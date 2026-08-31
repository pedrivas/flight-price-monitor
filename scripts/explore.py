"""Varre vários destinos a partir de uma origem e lista ida-e-volta abaixo de um teto.

Uso: PYTHONPATH=src python scripts/explore.py
A ferramenta principal monitora rotas fixas; isto é uma busca exploratória
one-off sobre uma lista de destinos candidatos.
"""
from __future__ import annotations

import sys
import time
from datetime import date

from fast_flights import FlightQuery, Passengers, create_query, get_flights
from fast_flights.exceptions import FlightsNotFound

ORIGIN = "GRU"
BUDGET = float(sys.argv[1]) if len(sys.argv) > 1 else 1800.0  # teto, override: python scripts/explore.py 1600
CURRENCY = "BRL"
ADULTS = 1
DEPARTS = [date(2026, 9, 4), date(2026, 9, 8), date(2026, 9, 11)]
RETURNS = [date(2026, 9, 18), date(2026, 9, 25)]

DESTS = {
    # Brasil
    "REC": "Recife", "SSA": "Salvador", "FOR": "Fortaleza", "NAT": "Natal",
    "MCZ": "Maceió", "JPA": "João Pessoa", "SLZ": "São Luís", "BEL": "Belém",
    "POA": "Porto Alegre", "CWB": "Curitiba", "FLN": "Florianópolis",
    "IGU": "Foz do Iguaçu", "BSB": "Brasília", "CNF": "Belo Horizonte",
    "GIG": "Rio de Janeiro", "VIX": "Vitória", "CGB": "Cuiabá", "GYN": "Goiânia",
    "BPS": "Porto Seguro", "IOS": "Ilhéus",
    # América do Sul
    "EZE": "Buenos Aires", "SCL": "Santiago", "MVD": "Montevidéu",
    "ASU": "Assunção", "LIM": "Lima", "BOG": "Bogotá", "MDE": "Medellín",
}


def cheapest_for(dst: str):
    best = None
    for dep in DEPARTS:
        for ret in RETURNS:
            query = create_query(
                flights=[
                    FlightQuery(date=dep.isoformat(), from_airport=ORIGIN, to_airport=dst),
                    FlightQuery(date=ret.isoformat(), from_airport=dst, to_airport=ORIGIN),
                ],
                trip="round-trip",
                seat="economy",
                passengers=Passengers(adults=ADULTS),
                currency=CURRENCY,
                language="pt-BR",
            )
            try:
                results = get_flights(query)
            except FlightsNotFound:
                continue
            except Exception as exc:  # rede / parsing
                print(f"  ! {dst} {dep}->{ret}: {exc}", file=sys.stderr)
                continue
            for fl in results:
                if not fl.price or fl.price <= 0 or not fl.flights:
                    continue
                if best is None or fl.price < best["price"]:
                    best = {
                        "price": float(fl.price),
                        "dep": dep,
                        "ret": ret,
                        "carrier": ", ".join(fl.airlines) if fl.airlines else str(fl.type),
                        "stops": max(len(fl.flights) - 1, 0),
                    }
            time.sleep(0.4)
    return best


def main() -> None:
    hits = []
    for code, name in DESTS.items():
        best = cheapest_for(code)
        if not best:
            print(f"    {code} {name}: sem resultado")
            continue
        mark = "OK " if best["price"] <= BUDGET else "   "
        print(
            f"{mark} {code} {name}: {CURRENCY} {best['price']:.0f} | "
            f"ida {best['dep']} volta {best['ret']} | {best['carrier']} | "
            f"{best['stops']} escala(s)"
        )
        if best["price"] <= BUDGET:
            hits.append((best["price"], code, name, best))

    print(f"\n===== abaixo de {CURRENCY} {BUDGET:.0f} =====")
    for price, code, name, b in sorted(hits):
        print(f"  {code} {name}: {CURRENCY} {price:.0f}  (ida {b['dep']}, volta {b['ret']}, {b['carrier']})")
    if not hits:
        print("  nada encontrado nas datas/destinos testados")


if __name__ == "__main__":
    main()
