"""Rota multidestino (open-jaw): chega em `dest`, volta saindo de `return_from`.

A fonte grátis não cota o bilhete multidestino único: a busca multi-city da
fast-flights volta sem voos, e uma ida e volta com aeroportos trocados é
tratada pelo Google como ida e volta normal (ADR-010). Então a rota vira 2
bilhetes só de ida com as datas amarradas:

    ida    origem → dest           em d
    volta  return_from → origem    em d+N  (N: dates.trip_for)
"""
from __future__ import annotations

from dataclasses import replace
from datetime import date

from .hubs import _quote_best, _trips
from .models import Offer, RouteQuery
from .sources.base import PriceSource


def search_openjaw(source: PriceSource, route: RouteQuery,
                   cache: dict | None = None, dates: list[date] | None = None) -> Offer | None:
    """Melhor soma ida + volta nas datas amostradas, ou None.

    Levanta NotImplementedError se a fonte não tem `quote`."""
    if not route.return_from or not route.return_after_days:
        raise ValueError(f"{route.name}: multidestino exige volta_de e NOITES")
    best: Offer | None = None
    for dep, ret in _trips(route, dates):
        out = _quote_best(source, cache, route, route.origin, route.dest, dep, None)
        back = _quote_best(source, cache, route, route.return_from, route.origin, ret, None)
        if out is None or back is None:
            continue
        total = out.price + back.price
        if best is None or total < best.price:
            best = Offer(
                route_key=route.key,  # a rota inteira é multidestino: a chave é a dela
                price=total,
                currency=route.currency,
                depart_date=dep,
                return_date=ret,
                carrier=f"{out.carrier} + {back.carrier}",
                stops=out.stops + back.stops,
                legs=[replace(out, route_key=route.key), replace(back, route_key=route.key)],
                origin=route.origin,
                dest=route.dest,
            )
    return best
