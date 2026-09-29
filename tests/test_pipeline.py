from __future__ import annotations

from datetime import date

import pytest

import monitor.main as main_mod
from conftest import seed_route
from monitor.models import RouteQuery
from monitor.storage import Storage


@pytest.fixture(autouse=True)
def _deterministic_fake(monkeypatch):
    monkeypatch.setattr("monitor.sources.fake.random.uniform", lambda a, b: 0.7)
    monkeypatch.setattr("monitor.sources.fake.random.choice", lambda seq: seq[0])


def test_run_sweep_alerts_and_prints(tmp_path, capsys):
    storage = Storage(tmp_path / "h.db")
    seed_route(storage, name="Pipeline test")
    alerts = main_mod.run_sweep(storage, dry_run=True, source_name="fake")
    assert alerts == 1
    out = capsys.readouterr().out
    assert "ALERTA (não enviado)" in out and "Pipeline test" in out


def test_run_sweep_records_history_under_id_key(tmp_path):
    storage = Storage(tmp_path / "h.db")
    rid = seed_route(storage)
    main_mod.run_sweep(storage, dry_run=True, source_name="fake")
    n = storage.conn.execute(
        "SELECT COUNT(*) FROM price_history WHERE route_key=?", (f"r{rid}",)
    ).fetchone()[0]
    assert n == 1


def test_run_sweep_survives_one_route_db_error(tmp_path, monkeypatch, capsys):
    import sqlite3

    storage = Storage(tmp_path / "h.db")
    seed_route(storage, name="Rota A")
    seed_route(storage, name="Rota B")

    real_record, calls = storage.record, {"n": 0}

    def flaky(offer):
        calls["n"] += 1
        if calls["n"] == 1:
            raise sqlite3.OperationalError("disk I/O error")
        return real_record(offer)

    monkeypatch.setattr(storage, "record", flaky)
    main_mod.run_sweep(storage, dry_run=True, source_name="fake")

    assert storage.conn.execute("SELECT COUNT(*) FROM price_history").fetchone()[0] == 1
    assert "[erro] Rota A" in capsys.readouterr().err


def test_real_sweep_without_telegram_degrades(tmp_path, capsys):
    storage = Storage(tmp_path / "h.db")
    seed_route(storage)
    alerts = main_mod.run_sweep(storage, dry_run=False, source_name="fake")  # não deve levantar
    assert alerts == 1
    assert "não enviado" in capsys.readouterr().err


def _keys(storage) -> set[str]:
    return {r[0] for r in storage.conn.execute("SELECT DISTINCT route_key FROM price_history")}


def test_sweep_with_hub_records_each_option_and_alerts_once(tmp_path, monkeypatch, capsys):
    from monitor.sources.fake import FakeSource

    storage = Storage(tmp_path / "h.db")
    rid = seed_route(storage, name="Com hub", hubs="LIS,MAD")
    # direto = 999999 × 0.7 (FakeSource.search); via LIS sai 500, via MAD 900
    src = FakeSource(prices={("GRU", "LIS"): 300, ("LIS", "REC"): 200,
                             ("GRU", "MAD"): 600, ("MAD", "REC"): 300})
    monkeypatch.setattr(main_mod, "get_source", lambda name: src)

    alerts = main_mod.run_sweep(storage, dry_run=True, source_name="fake")

    assert alerts == 1  # três opções aprovadas, um alerta só
    assert _keys(storage) == {f"r{rid}", f"r{rid}@LIS", f"r{rid}@MAD"}
    out = capsys.readouterr().out
    assert out.count("ALERTA (não enviado)") == 1
    assert "via Lisboa (2 passagens)" in out and "direto hoje" in out


def test_sweep_skips_hubs_when_source_has_no_quote(tmp_path, monkeypatch, capsys):
    from monitor.sources.base import PriceSource
    from monitor.sources.fake import FakeSource

    class SearchOnly(PriceSource):
        name = "searchonly"
        search = FakeSource.search

    storage = Storage(tmp_path / "h.db")
    rid = seed_route(storage, hubs="LIS")
    monkeypatch.setattr(main_mod, "get_source", lambda name: SearchOnly())

    assert main_mod.run_sweep(storage, dry_run=True, source_name="x") == 1  # o direto segue
    assert _keys(storage) == {f"r{rid}"}
    assert "estratégia de hub desligada" in capsys.readouterr().err


def test_tick_gates_sweep_by_interval(tmp_path, monkeypatch):
    db = tmp_path / "h.db"
    monkeypatch.setenv("MONITOR_DB_PATH", str(db))
    monkeypatch.setattr(
        main_mod, "load_routes_from_yaml",
        lambda *a: [RouteQuery(
            name="R", origin="GRU", dest="REC",
            depart_range=(date(2026, 11, 5), date(2026, 11, 20)),
            return_after_days=(5, 9), target_price=999999.0, drop_pct=20.0,
        )],
    )

    def count() -> int:
        return Storage(db).conn.execute("SELECT COUNT(*) FROM price_history").fetchone()[0]

    main_mod.tick(dry_run=True, source_name="fake", skip_bot=True)   # sem last_sweep → roda
    assert count() == 1 and Storage(db).kv_get("last_sweep_at")

    main_mod.tick(dry_run=True, source_name="fake", skip_bot=True)   # dentro do intervalo → pula
    assert count() == 1

    main_mod.tick(dry_run=True, source_name="fake", skip_bot=True, force_sweep=True)
    assert count() == 2


def test_command_flag_runs_handler_and_skips_sweep(tmp_path, monkeypatch, capsys):
    db = tmp_path / "h.db"
    monkeypatch.setenv("MONITOR_DB_PATH", str(db))
    monkeypatch.setattr(main_mod, "load_routes_from_yaml", lambda *a: [])

    # sem a barra inicial — run_command deve tolerar
    main_mod.tick(command="criar GRU BEL 2026-09-04..2026-09-11 7-21 1700", dry_run=True)

    s = Storage(db)
    assert len(s.list_routes()) == 1
    assert "criada" in capsys.readouterr().out
    assert s.conn.execute("SELECT COUNT(*) FROM price_history").fetchone()[0] == 0  # não varreu
    assert s.kv_get("last_sweep_at") is None


def test_tick_seeds_routes_from_yaml_once(tmp_path, monkeypatch):
    db = tmp_path / "h.db"
    monkeypatch.setenv("MONITOR_DB_PATH", str(db))
    seed = [RouteQuery(
        name="Semeada", origin="GRU", dest="REC",
        depart_range=(date(2026, 11, 5), date(2026, 11, 20)),
        return_after_days=(5, 9), target_price=999999.0,
    )]
    monkeypatch.setattr(main_mod, "load_routes_from_yaml", lambda *a: seed)

    main_mod.tick(dry_run=True, source_name="fake", skip_bot=True, skip_sweep=True)
    assert [r.name for r in Storage(db).list_routes()] == ["Semeada"]

    # segunda chamada não duplica
    main_mod.tick(dry_run=True, source_name="fake", skip_bot=True, skip_sweep=True)
    assert len(Storage(db).list_routes()) == 1


def test_sweep_open_jaw_alerts_with_both_legs(tmp_path, monkeypatch, capsys):
    from monitor.sources.fake import FakeSource

    storage = Storage(tmp_path / "h.db")
    rid = seed_route(storage, name="SAO→IST · ATH→SAO", origin="SAO", dest="IST", return_from="ATH",
                     hubs="LIS")  # hub é ignorado em multidestino
    src = FakeSource(prices={("SAO", "IST"): 4000, ("ATH", "SAO"): 2000})
    monkeypatch.setattr(main_mod, "get_source", lambda name: src)

    assert main_mod.run_sweep(storage, dry_run=True, source_name="fake") == 1
    assert _keys(storage) == {f"r{rid}"}
    assert storage.last_price(f"r{rid}") == 6000
    assert {(o, d) for o, d, *_ in src.calls} == {("SAO", "IST"), ("ATH", "SAO")}
    out = capsys.readouterr().out
    assert "chega em Istambul, volta de Atenas" in out and "direto hoje" not in out
