from __future__ import annotations

import random
from datetime import timedelta

from ..models import FlightLeg, Offer, RouteQuery
from .base import PriceSource


class FakeSource(PriceSource):
    """Fonte sintética para testar o pipeline sem credenciais.
    Uso: python -m monitor.main --dry-run --source fake"""

    name = "fake"

    def search(self, route: RouteQuery) -> list[Offer]:
        base = route.target_price or 1000
        dep = route.depart_range[0]
        out = []
        for i in range(5):
            price = round(base * random.uniform(0.6, 1.4), 0)
            dep_i = dep + timedelta(days=i)
            ret = None
            if route.return_after_days:
                ret = dep_i + timedelta(days=route.return_after_days[0])
            stops = random.choice([0, 0, 1])
            out.append(
                Offer(
                    route_key=route.key,
                    price=price,
                    currency=route.currency,
                    depart_date=dep_i,
                    return_date=ret,
                    carrier=random.choice(["LA", "G3", "AD", "TP"]),
                    stops=stops,
                    outbound=_fake_leg(route.origin, route.dest, stops),
                )
            )
        return out


def _fake_leg(origin: str, dest: str, stops: int) -> FlightLeg:
    factor = random.uniform(0.3, 1.0)  # reusa o fator já patchado nos testes
    if stops == 0:
        minutes = int(120 + factor * 600)
        return FlightLeg(airports=[origin, dest], seg_minutes=[minutes], layover_minutes=[], total_minutes=minutes)
    mid = random.choice(["GIG", "BSB", "MIA", "LIS"])
    a, b, layover = int(90 + factor * 300), int(90 + factor * 300), int(45 + factor * 120)
    return FlightLeg(
        airports=[origin, mid, dest], seg_minutes=[a, b], layover_minutes=[layover], total_minutes=a + b + layover
    )
