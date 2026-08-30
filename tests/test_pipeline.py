from __future__ import annotations

import pytest

import monitor.main as main_mod
from monitor.config import load_routes


@pytest.fixture(autouse=True)
def _deterministic_fake(monkeypatch):
    # fixa o fator aleatório da fonte fake: preço = base * 0.7
    monkeypatch.setattr("monitor.sources.fake.random.uniform", lambda a, b: 0.7)
    monkeypatch.setattr("monitor.sources.fake.random.choice", lambda seq: seq[0])

ROUTES_YAML = """
currency: BRL
routes:
  - name: "Pipeline test"
    origin: GRU
    dest: REC
    depart_range: ["2026-11-05", "2026-11-20"]
    return_after_days: [5, 9]
    adults: 1
    target_price: 999999      # garante alerta com a fonte fake
    drop_pct: 20
"""


def test_run_with_fake_source(tmp_path, monkeypatch, capsys):
    routes_file = tmp_path / "routes.yaml"
    routes_file.write_text(ROUTES_YAML, encoding="utf-8")

    monkeypatch.setattr(main_mod, "load_routes", lambda: load_routes(routes_file))
    monkeypatch.setenv("MONITOR_DB_PATH", str(tmp_path / "history.db"))

    alerts = main_mod.run(dry_run=True, source_name="fake")

    assert alerts == 1
    out = capsys.readouterr().out
    assert "ALERTA (dry-run)" in out
    assert "Pipeline test" in out


def test_run_dry_does_not_need_telegram_env(tmp_path, monkeypatch):
    routes_file = tmp_path / "routes.yaml"
    routes_file.write_text(ROUTES_YAML, encoding="utf-8")
    monkeypatch.setattr(main_mod, "load_routes", lambda: load_routes(routes_file))
    monkeypatch.setenv("MONITOR_DB_PATH", str(tmp_path / "history.db"))
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)

    # não deve levantar KeyError por falta de secrets
    assert main_mod.run(dry_run=True, source_name="fake") == 1


def test_history_is_persisted(tmp_path, monkeypatch):
    routes_file = tmp_path / "routes.yaml"
    routes_file.write_text(ROUTES_YAML, encoding="utf-8")
    monkeypatch.setattr(main_mod, "load_routes", lambda: load_routes(routes_file))
    db = tmp_path / "history.db"
    monkeypatch.setenv("MONITOR_DB_PATH", str(db))

    main_mod.run(dry_run=True, source_name="fake")

    import sqlite3

    n = sqlite3.connect(db).execute("SELECT COUNT(*) FROM price_history").fetchone()[0]
    assert n == 1
