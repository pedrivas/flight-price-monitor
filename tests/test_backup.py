from __future__ import annotations

from monitor import backup


def test_hours_since_last_backup_inf_without_history(storage):
    assert backup.hours_since_last_backup(storage) == float("inf")


def test_mark_and_check_gate(storage):
    backup.mark_backup_done(storage)
    assert backup.hours_since_last_backup(storage) < 1


def test_run_backup_skips_and_marks_done_without_par(storage, monkeypatch):
    monkeypatch.delenv("OCI_BACKUP_PAR_URL", raising=False)
    ok = backup.run_backup(storage)
    assert ok is False
    assert backup.hours_since_last_backup(storage) < 1  # marcado mesmo sem enviar, evita reverificar a cada tick


def test_run_backup_puts_named_snapshot(storage, monkeypatch):
    monkeypatch.setenv("OCI_BACKUP_PAR_URL", "https://example.com/backup")
    calls = {}

    class FakeResp:
        def raise_for_status(self):
            pass

    def fake_put(url, data, timeout):
        calls["url"] = url
        calls["data"] = data.read()
        return FakeResp()

    monkeypatch.setattr(backup.requests, "put", fake_put)
    ok = backup.run_backup(storage)

    assert ok is True
    assert calls["url"].startswith("https://example.com/backup/history-")
    assert calls["url"].endswith(".db")
    assert len(calls["data"]) > 0  # arquivo sqlite de verdade, não vazio
    assert backup.hours_since_last_backup(storage) < 1


def test_run_backup_failure_does_not_raise(storage, monkeypatch):
    monkeypatch.setenv("OCI_BACKUP_PAR_URL", "https://example.com/backup")

    def boom(*a, **kw):
        raise ConnectionError("rede caiu")

    monkeypatch.setattr(backup.requests, "put", boom)

    ok = backup.run_backup(storage)  # não deve propagar a exceção

    assert ok is False
    assert backup.hours_since_last_backup(storage) < 1  # marcado mesmo com falha
