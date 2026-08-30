from __future__ import annotations

from datetime import date

import pytest

from monitor.models import Offer, RouteQuery
from monitor.storage import Storage


@pytest.fixture
def storage(tmp_path) -> Storage:
    return Storage(tmp_path / "history.db")


@pytest.fixture
def route() -> RouteQuery:
    return RouteQuery(
        name="Teste GRU-REC",
        origin="GRU",
        dest="REC",
        depart_range=(date(2026, 11, 5), date(2026, 11, 20)),
        adults=1,
        return_after_days=(5, 9),
        target_price=900.0,
        drop_pct=20.0,
    )


def make_offer(route: RouteQuery, price: float) -> Offer:
    return Offer(
        route_key=route.key,
        price=price,
        currency=route.currency,
        depart_date=date(2026, 11, 10),
        return_date=date(2026, 11, 17),
        carrier="LATAM",
        stops=0,
    )
