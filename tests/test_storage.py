from __future__ import annotations

from datetime import datetime, timedelta, timezone

from conftest import make_offer


def _backdate(storage, route_key: str, days_ago: int, price: float) -> None:
    """Insere um ponto de histórico com data no passado (contorna o now())."""
    seen = (datetime.now(timezone.utc) - timedelta(days=days_ago)).strftime("%Y-%m-%dT%H:%M:%S")
    storage.conn.execute(
        "INSERT INTO price_history (route_key, price, currency, depart_date, seen_at) "
        "VALUES (?,?,?,?,?)",
        (route_key, price, "BRL", "2026-11-10", seen),
    )
    storage.conn.commit()


def test_median_none_without_history(storage, route):
    assert storage.median_last_days(route.key) is None


def test_median_odd_count(storage, route):
    for p in (1000, 1200, 800):
        storage.record(make_offer(route, p))
    assert storage.median_last_days(route.key) == 1000


def test_median_even_count(storage, route):
    for p in (1000, 1200, 800, 900):
        storage.record(make_offer(route, p))
    assert storage.median_last_days(route.key) == (900 + 1000) / 2


def test_median_ignores_points_outside_window(storage, route):
    _backdate(storage, route.key, days_ago=40, price=5000)
    storage.record(make_offer(route, 1000))
    assert storage.median_last_days(route.key, days=30) == 1000


def test_already_alerted_within_tolerance(storage, route):
    storage.mark_alerted(route.key, 1000.0)
    assert storage.already_alerted(route.key, 1015.0) is True   # +1.5%
    assert storage.already_alerted(route.key, 1050.0) is False  # +5%


def test_already_alerted_scoped_by_route(storage, route):
    storage.mark_alerted(route.key, 1000.0)
    assert storage.already_alerted("OUTRA-ROTA", 1000.0) is False


def test_mark_alerted_is_idempotent(storage, route):
    storage.mark_alerted(route.key, 1000.0)
    storage.mark_alerted(route.key, 1000.0)
    n = storage.conn.execute(
        "SELECT COUNT(*) FROM alerts_sent WHERE route_key=?", (route.key,)
    ).fetchone()[0]
    assert n == 1
