from __future__ import annotations

import sys
import time
from datetime import date, datetime, timedelta

from fast_flights import FlightQuery, Passengers, create_query, get_flights
from fast_flights.exceptions import FlightsNotFound

from ..dates import sample_dates
from ..models import FlightLeg, Offer, RouteQuery
from .base import PriceSource


def _to_datetime(simple_dt) -> datetime:
    y, m, d = simple_dt.date
    h, mi = simple_dt.time
    return datetime(y, m, d, h, mi)


def _build_leg(segments) -> FlightLeg | None:
    """Monta o FlightLeg a partir dos segmentos de UM trecho (ida ou volta)
    devolvidos pela fast-flights. `segments` é `Flights.flights` (SingleFlight)."""
    if not segments:
        return None
    try:
        airports = [segments[0].from_airport.code] + [s.to_airport.code for s in segments]
        seg_minutes = [int(s.duration) for s in segments]
        layover_minutes = [
            int((_to_datetime(segments[i + 1].departure) - _to_datetime(segments[i].arrival)).total_seconds() // 60)
            for i in range(len(segments) - 1)
        ]
        total_minutes = int(
            (_to_datetime(segments[-1].arrival) - _to_datetime(segments[0].departure)).total_seconds() // 60
        )
    except (AttributeError, TypeError, ValueError):
        return None  # dados de horário incompletos — segue sem o detalhe, não é fatal
    return FlightLeg(airports=airports, seg_minutes=seg_minutes, layover_minutes=layover_minutes, total_minutes=total_minutes)


class FastFlightsSource(PriceSource):
    """Dados ao vivo do Google Flights via a lib `fast-flights`.

    Não-oficial e sujeito a quebrar quando o Google muda o front-end.
    Uso pessoal apenas. Não requer chave/cadastro.
    """

    name = "fastflights"

    def __init__(self, language: str = "pt-BR", pause_s: float = 1.0) -> None:
        self.language = language
        self.pause_s = pause_s

    def search(self, route: RouteQuery) -> list[Offer]:
        offers: list[Offer] = []
        max_stops = 0 if route.nonstop else None

        for dep in sample_dates(*route.depart_range):
            legs = [
                FlightQuery(
                    date=dep.isoformat(),
                    from_airport=route.origin,
                    to_airport=route.dest,
                    max_stops=max_stops,
                )
            ]
            trip = "one-way"
            ret: date | None = None
            if route.return_after_days:
                # checa uma única duração de viagem (ponto médio do range),
                # para não multiplicar o nº de buscas
                lo, hi = route.return_after_days
                ret = dep + timedelta(days=(lo + hi) // 2)
                legs.append(
                    FlightQuery(
                        date=ret.isoformat(),
                        from_airport=route.dest,
                        to_airport=route.origin,
                        max_stops=max_stops,
                    )
                )
                trip = "round-trip"

            query = create_query(
                flights=legs,
                trip=trip,
                seat="economy",
                passengers=Passengers(adults=max(route.adults, 1)),
                currency=route.currency,
                language=self.language,
            )

            results = self._fetch(query, f"{route.name} {dep}")
            if results is None:
                continue

            for fl in results:
                if not fl.price or fl.price <= 0 or not fl.flights:
                    continue  # "preço indisponível"
                offers.append(
                    Offer(
                        route_key=route.key,
                        price=float(fl.price),
                        currency=route.currency,
                        depart_date=dep,
                        return_date=ret,
                        carrier=", ".join(fl.airlines) if fl.airlines else str(fl.type),
                        stops=max(len(fl.flights) - 1, 0),  # escalas do trecho de ida
                        outbound=_build_leg(fl.flights),
                    )
                )

            time.sleep(self.pause_s)  # gentileza com o Google

        return offers

    def _fetch(self, query, label: str):
        """get_flights com retry. O parser da lib levanta IndexError/KeyError em
        algumas respostas do Google — quase sempre transitório."""
        for attempt in range(3):
            try:
                return get_flights(query)
            except FlightsNotFound:
                return None
            except Exception as exc:  # parser frágil da fast-flights
                if attempt == 2:
                    print(f"[aviso] fastflights falhou em {label}: {exc}", file=sys.stderr)
                    return None
                time.sleep(1.5 * (attempt + 1))
