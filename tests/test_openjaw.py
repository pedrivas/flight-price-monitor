from __future__ import annotations

from datetime import date

import pytest

from monitor.models import RouteQuery
from monitor.openjaw import search_openjaw
from monitor.sources.fake import FakeSource


@pytest.fixture(autouse=True)
def _deterministic_fake(monkeypatch):
    monkeypatch.setattr("monitor.sources.fake.random.uniform", lambda a, b: 0.7)


def _route(**kw) -> RouteQuery:
    base = dict(id=3, name="SAO→IST · ATH→SAO", origin="SAO", dest="IST", return_from="ATH",
                depart_range=(date(2027, 4, 1), date(2027, 4, 15)), return_after_days=(10, 14))
    base.update(kw)
    return RouteQuery(**base)


def test_two_one_ways_with_linked_dates():
    src = FakeSource(prices={("SAO", "IST"): 4245, ("ATH", "SAO"): 2358})
    offer = search_openjaw(src, _route(), dates=[date(2027, 4, 5)])
    out, back = offer.legs
    assert (out.origin, out.dest, out.depart_date, out.return_date) == ("SAO", "IST", date(2027, 4, 5), None)
    assert (back.origin, back.dest, back.depart_date, back.return_date) == ("ATH", "SAO", date(2027, 4, 17), None)
    assert offer.price == 4245 + 2358
    assert offer.route_key == "r3" and offer.via is None  # a chave é a da própria rota
    assert offer.return_date == date(2027, 4, 17)


def test_picks_cheapest_date():
    src = FakeSource()
    prices = iter([900, 900, 500, 400])  # 1ª data soma 1800, 2ª soma 900

    def quote(*a, **k):
        o = FakeSource.quote(src, *a, **k)
        o[0].price = float(next(prices))
        return o

    src.quote = quote
    offer = search_openjaw(src, _route(), dates=[date(2027, 4, 2), date(2027, 4, 9)])
    assert offer.price == 900 and offer.depart_date == date(2027, 4, 9)


def test_requires_nights_and_return_airport():
    with pytest.raises(ValueError):
        search_openjaw(FakeSource(), _route(return_after_days=None))
    with pytest.raises(ValueError):
        search_openjaw(FakeSource(), _route(return_from=None))
