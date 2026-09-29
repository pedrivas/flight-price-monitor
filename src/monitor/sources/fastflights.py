from __future__ import annotations

import json
import sys
import time
from datetime import date, datetime, timedelta

from fast_flights import FlightQuery, Passengers, create_query
from fast_flights.exceptions import FlightsNotFound
from fast_flights.fetcher import fetch_flights_html
from fast_flights.model import Airport, Flights, SimpleDatetime, SingleFlight
from fast_flights.parser import _parse_time
from selectolax.lexbor import LexborHTMLParser

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


# Blocos de voos no payload do Google: 2 = "Melhores voos", 3 = "Outros voos".
_RESULT_BLOCKS = (2, 3)


def _parse_segment(sf) -> SingleFlight:
    return SingleFlight(
        from_airport=Airport(code=sf[3], name=sf[4]),
        to_airport=Airport(code=sf[6], name=sf[5]),
        departure=SimpleDatetime(date=tuple(sf[20]), time=_parse_time(sf[8])),
        arrival=SimpleDatetime(date=tuple(sf[21]), time=_parse_time(sf[10])),
        duration=sf[11],
        plane_type=sf[17],
    )


def parse_payload(payload: list) -> list[Flights]:
    """Lê os voos dos DOIS blocos do payload.

    O parser da fast-flights (3.1) só lê o bloco 3 e ignora os "Melhores
    voos" (bloco 2) — que é onde o Google costuma pôr a opção mais barata
    (SAO⇄IST: R$ 6.171 no bloco 2 × R$ 6.863 no 3). Ele também quebra quando
    falta a lista de companhias em payload[7], que aqui é irrelevante."""
    out: list[Flights] = []
    seen = set()
    for idx in _RESULT_BLOCKS:
        block = payload[idx] if len(payload) > idx else None
        if not block or not block[0]:
            continue
        for item in block[0]:
            try:
                flight, price = item[0], item[1][0][1]
                segments = [_parse_segment(sf) for sf in flight[2]]
            except (IndexError, TypeError):
                continue  # item malformado não derruba o resto
            key = (price, tuple((s.from_airport.code, s.to_airport.code, s.departure.date, s.departure.time)
                                for s in segments))
            if key in seen:
                continue  # mesmo voo nos dois blocos
            seen.add(key)
            out.append(Flights(type=flight[0], price=price, airlines=flight[1], flights=segments, carbon=None))
    return out


def parse_html(html: str) -> list[Flights]:
    script = LexborHTMLParser(html).css_first(r"script.ds\:1")
    if script is None:
        raise ValueError("resposta sem o bloco de dados (script.ds:1)")
    data = script.text().split("data:", 1)[1].rsplit(",", 1)[0]
    if data.endswith("errorHasStatus: true"):
        raise FlightsNotFound("no flights found; received error")
    return parse_payload(json.loads(data))


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
        for dep in sample_dates(*route.depart_range):
            ret: date | None = None
            if route.return_after_days:
                # checa uma única duração de viagem (ponto médio do range),
                # para não multiplicar o nº de buscas
                lo, hi = route.return_after_days
                ret = dep + timedelta(days=(lo + hi) // 2)
            offers += self.quote(
                route.origin, route.dest, dep, ret,
                adults=route.adults, currency=route.currency, nonstop=route.nonstop,
                route_key=route.key,
            )
        return offers

    def quote(
        self,
        origin: str,
        dest: str,
        depart: date,
        return_date: date | None = None,
        *,
        adults: int = 1,
        currency: str = "BRL",
        nonstop: bool = False,
        route_key: str = "",
    ) -> list[Offer]:
        max_stops = 0 if nonstop else None
        legs = [FlightQuery(date=depart.isoformat(), from_airport=origin, to_airport=dest, max_stops=max_stops)]
        if return_date:
            legs.append(
                FlightQuery(date=return_date.isoformat(), from_airport=dest, to_airport=origin, max_stops=max_stops)
            )
        query = create_query(
            flights=legs,
            trip="round-trip" if return_date else "one-way",
            seat="economy",
            passengers=Passengers(adults=max(adults, 1)),
            currency=currency,
            language=self.language,
        )
        results = self._fetch(query, f"{origin}->{dest} {depart}")
        time.sleep(self.pause_s)  # gentileza com o Google
        if results is None:
            return []

        offers: list[Offer] = []
        for fl in results:
            if not fl.price or fl.price <= 0 or not fl.flights:
                continue  # "preço indisponível"
            offers.append(
                Offer(
                    route_key=route_key,
                    price=float(fl.price),
                    currency=currency,
                    depart_date=depart,
                    return_date=return_date,
                    carrier=", ".join(fl.airlines) if fl.airlines else str(fl.type),
                    stops=max(len(fl.flights) - 1, 0),  # escalas do trecho de ida
                    outbound=_build_leg(fl.flights),
                    origin=origin,
                    dest=dest,
                )
            )
        return offers

    def _fetch(self, query, label: str):
        """Busca + parse próprio (parse_html) com retry — rede e respostas
        truncadas do Google falham de vez em quando, quase sempre transitório."""
        for attempt in range(3):
            try:
                return parse_html(fetch_flights_html(query))
            except FlightsNotFound:
                return None
            except Exception as exc:  # parser frágil da fast-flights
                if attempt == 2:
                    print(f"[aviso] fastflights falhou em {label}: {exc}", file=sys.stderr)
                    return None
                time.sleep(1.5 * (attempt + 1))
