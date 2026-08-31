from __future__ import annotations

from datetime import date

import pytest

from monitor import explore
from monitor.explore import (
    ExploreHit,
    _parse_range,
    _window_to_nights,
    format_results,
    run_explore,
)
from monitor.models import Offer
from monitor.sources.fake import FakeSource


@pytest.fixture(autouse=True)
def _deterministic_fake(monkeypatch):
    monkeypatch.setattr("monitor.sources.fake.random.uniform", lambda a, b: 0.7)
    monkeypatch.setattr("monitor.sources.fake.random.choice", lambda seq: seq[0])


DEP = (date(2026, 10, 1), date(2026, 10, 8))
RET = (date(2026, 10, 15), date(2026, 10, 22))


# --- helpers -------------------------------------------------------------
def test_window_to_nights_uses_midpoints():
    # meio da ida = 04/out, meio da volta = 18/out -> 14 noites
    assert _window_to_nights(DEP, RET) == 14


def test_window_to_nights_floor_one():
    d = (date(2026, 10, 1), date(2026, 10, 1))
    assert _window_to_nights(d, d) == 1


def test_parse_range_ok():
    assert _parse_range("2026-10-01..2026-10-08") == DEP


@pytest.mark.parametrize("bad", ["2026-10-01", "xxxx..yyyy", "2026-10-08..2026-10-01"])
def test_parse_range_rejects(bad):
    import argparse

    with pytest.raises(argparse.ArgumentTypeError):
        _parse_range(bad)


# --- run_explore -------------------------------------------------------
def test_run_explore_filters_and_sorts():
    # FakeSource: preço = base(=target_price ou 1000) * 0.7. Sem target -> base 1000 -> 700.
    dests = {"AAA": "A", "BBB": "B", "CCC": "C"}
    under, near = run_explore("GRU", DEP, RET, max_price=800, dests=dests, source=FakeSource())
    assert [h.code for h in under] == ["AAA", "BBB", "CCC"]  # todos a 700, ordenados
    assert all(h.price <= 800 for h in under)
    assert near == []


def test_run_explore_near_miss_band():
    dests = {"AAA": "A"}
    # 700 fica entre 650 e 650*1.2=780 -> near-miss
    under, near = run_explore("GRU", DEP, RET, max_price=650, dests=dests, source=FakeSource())
    assert under == []
    assert [h.code for h in near] == ["AAA"]

    # teto 500: 700 > 500*1.2=600 -> nem near-miss
    under, near = run_explore("GRU", DEP, RET, max_price=500, dests=dests, source=FakeSource())
    assert under == [] and near == []


def test_run_explore_only_queries_given_destinations():
    seen = []

    class SpySource(FakeSource):
        def search(self, route):
            seen.append(route.dest)
            return super().search(route)

    run_explore("GRU", DEP, RET, max_price=800, dests={"REC": "Recife", "SSA": "Salvador"}, source=SpySource())
    assert sorted(seen) == ["REC", "SSA"]


# --- format_results ---------------------------------------------------
def _hit(code, name, price):
    return ExploreHit(code, name, Offer(
        route_key="x", price=price, currency="BRL",
        depart_date=date(2026, 10, 4), return_date=date(2026, 10, 18),
        carrier="LATAM", stops=0,
    ))


def test_format_results_lists_and_escapes():
    out = format_results([_hit("REC", "Recife & cia", 700)], [_hit("GIG", "Rio", 1900)], "GRU", 1800, "BRL")
    assert "Explore GRU" in out
    assert "Recife &amp; cia (REC)" in out
    assert "quase lá" in out and "Rio (GIG)" in out


def test_format_results_empty():
    out = format_results([], [], "GRU", 1800, "BRL")
    assert "Nada encontrado" in out


# --- main -----------------------------------------------------------
def test_main_dry_run_does_not_send(monkeypatch, capsys):
    calls = {"sent": 0}

    def fake_run(origin, dep, ret, maxp, **kw):
        assert dep == DEP and ret == RET and maxp == 1500.0
        return [_hit("REC", "Recife", 700)], []

    monkeypatch.setattr(explore, "run_explore", fake_run)
    monkeypatch.setattr(explore.TelegramClient, "send_message",
                        lambda self, text, chat_id=None: calls.__setitem__("sent", calls["sent"] + 1))

    explore.main([
        "--depart", "2026-10-01..2026-10-08", "--return", "2026-10-15..2026-10-22",
        "--max", "1500", "--destinations", "REC", "--dry-run",
    ])
    assert calls["sent"] == 0
    assert "Explore GRU" in capsys.readouterr().out
