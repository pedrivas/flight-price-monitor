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


def test_hubs_roundtrip(storage):
    rid = seed_route(storage, hubs="LIS,MAD")
    assert storage.get_route(rid).hubs == ["LIS", "MAD"]
    storage.update_route(rid, hubs=None)
    assert storage.get_route(rid).hubs == []


def test_migration_adds_hubs_column_to_existing_db(tmp_path, capsys):
    # o banco da VM foi criado antes da coluna existir
    import sqlite3

    db = tmp_path / "old.db"
    conn = sqlite3.connect(db)
    conn.execute(
        """CREATE TABLE routes (
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, origin TEXT NOT NULL,
            dest TEXT NOT NULL, depart_from TEXT NOT NULL, depart_to TEXT NOT NULL,
            return_min INTEGER, return_max INTEGER, adults INTEGER NOT NULL DEFAULT 1,
            target_price REAL, drop_pct REAL, nonstop INTEGER NOT NULL DEFAULT 0,
            currency TEXT NOT NULL DEFAULT 'BRL', active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL)"""
    )
    conn.execute(
        "INSERT INTO routes (name, origin, dest, depart_from, depart_to, created_at) "
        "VALUES ('Antiga', 'GRU', 'LIS', '2027-04-01', '2027-04-30', '2026-01-01')"
    )
    conn.commit()
    conn.close()

    s = Storage(db)
    assert s.get_route(1).hubs == []
    assert "coluna routes.hubs adicionada" in capsys.readouterr().out
    Storage(db)  # idempotente: segunda abertura não tenta de novo
    assert "adicionada" not in capsys.readouterr().out


def test_best_last_price_picks_cheapest_option(storage):
    from dataclasses import replace

    from conftest import make_offer

    r = storage.get_route(seed_route(storage, hubs="LIS,MAD"))
    assert storage.best_last_price(r) == (None, None)
    storage.record(make_offer(r, 3800.0))
    storage.record(replace(make_offer(r, 3100.0), route_key=f"{r.key}@MAD"))
    storage.record(replace(make_offer(r, 3300.0), route_key=f"{r.key}@LIS"))
    assert storage.best_last_price(r) == (3100.0, "MAD")


def test_migration_tolerates_concurrent_add(tmp_path, monkeypatch):
    # dois workers abrem o banco juntos: ambos veem a coluna faltando, um perde a corrida
    import monitor.storage as storage_mod

    db = tmp_path / "race.db"
    Storage(db)  # já tem a coluna
    monkeypatch.setattr(storage_mod, "_ADDED_ROUTE_COLUMNS", {"hubs": "TEXT"})
    s = Storage.__new__(Storage)
    s.conn = Storage(db).conn
    real = s.conn

    class StalePragma:
        def execute(self, sql, *a):
            if sql.startswith("PRAGMA table_info"):
                return iter([])  # finge que a coluna não existe
            return real.execute(sql, *a)

    s.conn = StalePragma()
    s._migrate()  # não levanta "duplicate column name"
