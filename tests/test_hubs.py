from __future__ import annotations

from datetime import date, timedelta

import pytest

from monitor.hubs import (
    GLOBAL_CANDIDATES,
    LAYOVER_DAYS,
    candidate_hubs,
    discover,
    format_discovery,
    hubs_report,
    search_via,
)
from monitor.models import RouteQuery
from monitor.sources.base import PriceSource
from monitor.sources.fake import FakeSource


@pytest.fixture(autouse=True)
def _deterministic_fake(monkeypatch):
    monkeypatch.setattr("monitor.sources.fake.random.uniform", lambda a, b: 0.7)


def _route(nights=(10, 14), **kw) -> RouteQuery:
    base = dict(
        id=7, name="SAO→ATH", origin="SAO", dest="ATH",
        depart_range=(date(2027, 4, 1), date(2027, 4, 30)), return_after_days=nights,
    )
    base.update(kw)
    return RouteQuery(**base)


def test_roundtrip_inner_ticket_fits_inside_outer_with_layover():
    src = FakeSource()
    offer = search_via(src, _route(), "LIS", dates=[date(2027, 4, 10)])
    outer, inner = offer.legs
    assert (outer.origin, outer.dest) == ("SAO", "LIS")
    assert (inner.origin, inner.dest) == ("LIS", "ATH")
    assert outer.depart_date == date(2027, 4, 10)
    assert outer.return_date == date(2027, 4, 22)  # 12 noites = ponto médio de 10-14
    assert inner.depart_date == outer.depart_date + timedelta(days=LAYOVER_DAYS)
    assert inner.return_date == outer.return_date - timedelta(days=LAYOVER_DAYS)


def test_via_offer_sums_legs_and_uses_own_history_key():
    src = FakeSource(prices={("SAO", "LIS"): 2400, ("LIS", "ATH"): 600})
    offer = search_via(src, _route(), "LIS", dates=[date(2027, 4, 10)])
    assert offer.price == 3000
    assert offer.route_key == "r7@LIS" and offer.via == "LIS"
    assert all(leg.route_key == "r7@LIS" for leg in offer.legs)
    assert offer.stops == 1  # dois voos diretos + a troca no hub


def test_short_trip_skips_hub():
    src = FakeSource()
    assert search_via(src, _route(nights=(3, 4)), "LIS") is None
    assert src.calls == []


def test_one_way_uses_layover_on_second_leg():
    src = FakeSource()
    offer = search_via(src, _route(nights=None), "MAD", dates=[date(2027, 4, 10)])
    outer, inner = offer.legs
    assert outer.return_date is None and inner.return_date is None
    assert inner.depart_date == date(2027, 4, 12)


def test_cache_avoids_repeating_shared_legs():
    src = FakeSource()
    cache: dict = {}
    dates = [date(2027, 4, 10)]
    search_via(src, _route(), "LIS", cache, dates)
    search_via(src, _route(id=8, name="outra"), "LIS", cache, dates)  # mesmos trechos
    assert len(src.calls) == 2


def test_discover_keeps_only_hubs_that_beat_direct():
    src = FakeSource(prices={
        ("SAO", "ATH"): 3800,
        ("SAO", "LIS"): 2400, ("LIS", "ATH"): 600,   # 3000: ganha
        ("SAO", "MAD"): 2500, ("MAD", "ATH"): 700,   # 3200: ganha
        ("SAO", "CDG"): 3500, ("CDG", "ATH"): 700,   # 4200: perde
    })
    result = discover(src, _route(), candidates=["CDG", "MAD", "LIS"])
    assert result.chosen == ["LIS", "MAD"]
    assert [h for h, _ in result.ranking] == ["LIS", "MAD", "CDG"]
    text = format_discovery(_route(), result)
    assert "Monitorando direto + LIS" in text and "<pre>" in text


def test_discover_reports_when_no_hub_wins():
    src = FakeSource(prices={("SAO", "ATH"): 1000, ("SAO", "LIS"): 900, ("LIS", "ATH"): 900})
    result = discover(src, _route(), candidates=["LIS"])
    assert result.chosen == []
    assert "Nenhum hub bateu" in format_discovery(_route(), result)


def test_candidates_by_destination_region():
    eu = candidate_hubs("GRU", "ATH")
    assert "LIS" in eu and "MAD" in eu and "MIA" not in eu
    assert "MIA" in candidate_hubs("GRU", "JFK")
    assert "LIS" not in candidate_hubs("GRU", "LIS")  # destino nunca é hub de si mesmo


def test_unknown_destination_falls_back_to_global():
    assert candidate_hubs("GRU", "XYZ") == GLOBAL_CANDIDATES


def test_source_without_quote_raises():
    class NoQuote(PriceSource):
        name = "noquote"

        def search(self, route):
            return []

    with pytest.raises(NotImplementedError):
        search_via(NoQuote(), _route(), "LIS", dates=[date(2027, 4, 10)])


def test_hubs_report_groups_by_month():
    src = FakeSource(prices={("SAO", "ATH"): 3800, ("SAO", "LIS"): 2400, ("LIS", "ATH"): 600})
    route = _route(depart_range=(date(2027, 4, 1), date(2027, 5, 31)))
    text = hubs_report(src, route, ["LIS"])
    assert "abril" in text and "maio" in text
    assert "melhor: LIS" in text and "Passagens separadas" in text
