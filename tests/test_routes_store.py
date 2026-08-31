from __future__ import annotations

from datetime import date

from conftest import seed_route

from monitor.models import RouteQuery
from monitor.storage import Storage


def test_add_and_list(storage):
    rid = seed_route(storage, name="GRU→BEL", dest="BEL")
    routes = storage.list_routes()
    assert len(routes) == 1
    r = routes[0]
    assert r.id == rid
    assert r.origin == "GRU" and r.dest == "BEL"
    assert r.depart_range == (date(2026, 11, 5), date(2026, 11, 20))
    assert r.return_after_days == (5, 9)
    assert r.key == f"r{rid}"


def test_one_way_route_maps_to_none(storage):
    seed_route(storage, return_min=None, return_max=None)
    assert storage.list_routes()[0].return_after_days is None


def test_update_route(storage):
    rid = seed_route(storage)
    assert storage.update_route(rid, target_price=1600.0, name="novo nome")
    r = storage.get_route(rid)
    assert r.target_price == 1600.0 and r.name == "novo nome"


def test_update_unknown_route_returns_false(storage):
    assert storage.update_route(999, target_price=1.0) is False


def test_soft_delete_hides_from_active_list(storage):
    rid = seed_route(storage)
    storage.set_route_active(rid, False)
    assert storage.list_routes(active_only=True) == []
    assert len(storage.list_routes(active_only=False)) == 1


def test_seed_is_idempotent(storage):
    routes = [RouteQuery(
        name="X", origin="GRU", dest="REC",
        depart_range=(date(2026, 11, 5), date(2026, 11, 20)), target_price=900.0,
    )]
    assert storage.seed_routes(routes) == 1
    assert storage.seed_routes(routes) == 0
    assert len(storage.list_routes()) == 1


def test_kv_roundtrip(storage):
    assert storage.kv_get("x") is None
    storage.kv_set("x", "42")
    assert storage.kv_get("x") == "42"
    storage.kv_set("x", "99")
    assert storage.kv_get("x") == "99"


def test_hours_since_last_sweep(storage):
    assert storage.hours_since_last_sweep() == float("inf")
    storage.mark_sweep_done()
    assert storage.hours_since_last_sweep() < 1


def test_last_price(storage):
    from conftest import make_offer

    r = storage.get_route(seed_route(storage))
    assert storage.last_price(r.key) is None
    storage.record(make_offer(r, 1234.0))
    assert storage.last_price(r.key) == 1234.0
