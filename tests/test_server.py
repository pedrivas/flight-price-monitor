from __future__ import annotations

import queue
import threading
import time
from http.server import ThreadingHTTPServer

import pytest
import requests

from monitor import server as server_mod
from monitor.bot import Job
from monitor.storage import Storage


# --- Handler HTTP: servidor real numa porta efêmera -------------------------
@pytest.fixture
def running_server(monkeypatch):
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "s3cret")
    fast_q: queue.Queue = queue.Queue()
    handler_cls = type("TestHandler", (server_mod.Handler,), {"fast_queue": fast_q})
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler_cls)
    port = httpd.server_address[1]
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{port}", fast_q
    httpd.shutdown()
    t.join(timeout=5)


def test_healthz(running_server):
    base, _q = running_server
    r = requests.get(f"{base}/healthz", timeout=5)
    assert r.status_code == 200


def test_unknown_path_404(running_server):
    base, _q = running_server
    r = requests.get(f"{base}/nada", timeout=5)
    assert r.status_code == 404


def test_webhook_rejects_missing_secret(running_server):
    base, q = running_server
    r = requests.post(f"{base}{server_mod.WEBHOOK_PATH}", json={"update_id": 1}, timeout=5)
    assert r.status_code == 401
    assert q.empty()


def test_webhook_rejects_wrong_secret(running_server):
    base, q = running_server
    r = requests.post(
        f"{base}{server_mod.WEBHOOK_PATH}",
        json={"update_id": 1},
        headers={"X-Telegram-Bot-Api-Secret-Token": "errado"},
        timeout=5,
    )
    assert r.status_code == 401
    assert q.empty()


def test_webhook_wrong_path_404(running_server):
    base, _q = running_server
    r = requests.post(
        f"{base}/outro/caminho", json={}, headers={"X-Telegram-Bot-Api-Secret-Token": "s3cret"}, timeout=5
    )
    assert r.status_code == 404


def test_webhook_accepts_and_queues(running_server):
    base, q = running_server
    r = requests.post(
        f"{base}{server_mod.WEBHOOK_PATH}",
        json={"update_id": 42, "message": {"text": "/monitorias", "chat": {"id": 1}}},
        headers={"X-Telegram-Bot-Api-Secret-Token": "s3cret"},
        timeout=5,
    )
    assert r.status_code == 200
    update = q.get(timeout=2)
    assert update["update_id"] == 42


# --- worker rápido: dedupe por update_id ------------------------------------
# Storage não é thread-safe entre conexões compartilhadas (check_same_thread do
# sqlite3): cada teste aponta o Storage() do worker pro MESMO arquivo, mas com
# uma conexão nova criada dentro da própria thread do worker — igual acontece
# em produção. Pra conferir o estado depois, reabrimos o arquivo na thread do teste.
def test_fast_worker_dedupes_by_update_id(tmp_path, fake_telegram, monkeypatch):
    db_path = tmp_path / "h.db"
    monkeypatch.setattr(server_mod, "Storage", lambda: Storage(db_path))
    monkeypatch.setattr(server_mod, "TelegramClient", lambda: fake_telegram)
    monkeypatch.setenv("TELEGRAM_ALLOWED_CHAT_IDS", "1")

    fast_q: queue.Queue = queue.Queue()
    slow_q: queue.Queue = queue.Queue()
    t = threading.Thread(target=server_mod._fast_worker, args=(fast_q, slow_q))
    t.start()

    update = {"update_id": 10, "message": {"text": "/monitorias", "chat": {"id": 1}}}
    fast_q.put(update)
    fast_q.put(update)  # reenvio do Telegram (timeout no ack)
    fast_q.put(None)
    t.join(timeout=5)

    assert len(fake_telegram.sent) == 1
    assert Storage(db_path).kv_get("telegram_offset") == "10"


def test_fast_worker_forwards_job_to_slow_queue(tmp_path, fake_telegram, monkeypatch):
    db_path = tmp_path / "h.db"
    monkeypatch.setattr(server_mod, "Storage", lambda: Storage(db_path))
    monkeypatch.setattr(server_mod, "TelegramClient", lambda: fake_telegram)
    monkeypatch.setenv("TELEGRAM_ALLOWED_CHAT_IDS", "1")

    fast_q: queue.Queue = queue.Queue()
    slow_q: queue.Queue = queue.Queue()
    t = threading.Thread(target=server_mod._fast_worker, args=(fast_q, slow_q))
    t.start()
    fast_q.put({"update_id": 1, "message": {"text": "/varrer", "chat": {"id": 1}}})
    fast_q.put(None)
    t.join(timeout=5)

    job = slow_q.get(timeout=2)
    assert isinstance(job, Job) and job.kind == "sweep"
    assert len(fake_telegram.sent) == 1  # o ack ("varredura forçada...") já saiu


# --- worker lento: tick vs. job explícito -----------------------------------
def test_slow_worker_dispatches_tick_and_jobs(monkeypatch, storage):
    calls = []
    monkeypatch.setattr(server_mod, "Storage", lambda: storage)
    monkeypatch.setattr(server_mod, "_maybe_run_gated_jobs", lambda s: calls.append("tick"))
    monkeypatch.setattr(server_mod, "run_job", lambda job, s: calls.append(("job", job.kind)))

    slow_q: queue.Queue = queue.Queue()
    t = threading.Thread(target=server_mod._slow_worker, args=(slow_q,))
    t.start()
    slow_q.put(Job(kind="tick"))
    slow_q.put(Job(kind="explore"))
    slow_q.put(None)
    t.join(timeout=5)

    assert calls == ["tick", ("job", "explore")]


def test_slow_worker_handles_backup_kind(monkeypatch, storage):
    calls = []
    monkeypatch.setattr(server_mod, "Storage", lambda: storage)
    monkeypatch.setattr(server_mod.backup, "run_backup", lambda s: calls.append("backup"))

    slow_q: queue.Queue = queue.Queue()
    t = threading.Thread(target=server_mod._slow_worker, args=(slow_q,))
    t.start()
    slow_q.put(Job(kind="backup"))
    slow_q.put(None)
    t.join(timeout=5)

    assert calls == ["backup"]


# --- gate de 6h --------------------------------------------------------------
def test_maybe_run_gated_jobs_runs_once_then_gates(storage, monkeypatch):
    calls = {"n": 0}
    monkeypatch.setattr(server_mod.main_mod, "run_sweep", lambda *a, **kw: calls.__setitem__("n", calls["n"] + 1))

    server_mod._maybe_run_gated_jobs(storage)
    assert calls["n"] == 1
    assert storage.hours_since_last_sweep() < 1

    server_mod._maybe_run_gated_jobs(storage)
    assert calls["n"] == 1  # gate fechado logo em seguida — não roda de novo


# --- scheduler: enfileira ticks periodicamente -------------------------------
def test_scheduler_enqueues_ticks_until_shutdown(monkeypatch):
    monkeypatch.setattr(server_mod, "SCHEDULER_INTERVAL_S", 0.03)
    slow_q: queue.Queue = queue.Queue()
    shutdown = threading.Event()
    t = threading.Thread(target=server_mod._scheduler, args=(slow_q, shutdown))
    t.start()
    time.sleep(0.2)
    shutdown.set()
    t.join(timeout=2)

    n = 0
    while not slow_q.empty():
        job = slow_q.get()
        assert job.kind == "tick"
        n += 1
    assert n >= 2
