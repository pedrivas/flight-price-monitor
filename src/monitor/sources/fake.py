from __future__ import annotations

import random
from datetime import timedelta

from ..models import Offer, RouteQuery
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
            out.append(
                Offer(
                    route_key=route.key,
                    price=price,
                    currency=route.currency,
                    depart_date=dep_i,
                    return_date=ret,
                    carrier=random.choice(["LA", "G3", "AD", "TP"]),
                    stops=random.choice([0, 0, 1]),
                )
            )
        return out
