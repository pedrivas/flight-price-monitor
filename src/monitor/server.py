"""Processo long-running: recebe o webhook do Telegram e roda a varredura de
6h e o backup diário num horário previsível, em vez de depender do cron do
GitHub Actions. Ver ADR-008.

    python -m monitor.server

Arquitetura (ver ADR-008 pro porquê):

    POST /webhook/flight-tg ──▶ valida secret ──▶ 200 na hora ──▶ fila rápida
                                                                       │
    worker rápido (handle_update, Storage própria) ───────────────────┘
       │ comando comum: responde direto
       └ /explorar ou /varrer: responde "rodando..." e repassa pra fila lenta

    worker lento (Storage própria) ◀── fila lenta ◀── scheduler (tick 1/min)
       roda run_sweep / run_explore / backup — pode demorar minutos, não
       trava o worker rápido nem as respostas de comando.

Cada worker abre sua própria conexão SQLite (WAL + busy_timeout no
Storage.__init__ aguentam os dois escritores).
"""
from __future__ import annotations

import json
import os
import queue
import signal
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import backup
from . import main as main_mod
from .bot import Job, _allowed_chat_ids, handle_update, run_job
from .storage import Storage
from .telegram import TelegramClient

WEBHOOK_PATH = os.environ.get("WEBHOOK_PATH", "/webhook/flight-tg")
PORT = int(os.environ.get("PORT", "8080"))
SCHEDULER_INTERVAL_S = 60
JOIN_TIMEOUT_S = 25  # dá tempo de uma varredura/explore em curso terminar no SIGTERM


def _maybe_run_gated_jobs(storage: Storage) -> None:
    """Roda no worker lento (sempre a mesma thread) — os dois gates e as
    duas escritas ficam serializados entre si, sem precisar de lock extra."""
    if storage.hours_since_last_sweep() >= main_mod.SWEEP_INTERVAL_H:
        main_mod.run_sweep(storage, dry_run=False, source_name=os.environ.get("PRICE_SOURCE", "fastflights"))
        storage.mark_sweep_done()
    if backup.hours_since_last_backup(storage) >= backup.BACKUP_INTERVAL_H:
        backup.run_backup(storage)


def _fast_worker(fast_queue: "queue.Queue", slow_queue: "queue.Queue") -> None:
    storage = Storage()
    telegram = TelegramClient()
    allowed = _allowed_chat_ids()
    while True:
        update = fast_queue.get()
        if update is None:  # sentinela de shutdown
            return
        update_id = update.get("update_id")
        if update_id is not None:
            last = storage.kv_get("telegram_offset")
            if last and update_id <= int(last):
                continue  # reenvio do Telegram por timeout — já tratado
            storage.kv_set("telegram_offset", str(update_id))
        try:
            handle_update(update, storage, telegram, allowed, on_job=slow_queue.put)
        except Exception:
            import traceback

            traceback.print_exc()


def _slow_worker(slow_queue: "queue.Queue") -> None:
    storage = Storage()
    while True:
        job: Job | None = slow_queue.get()
        if job is None:
            return
        try:
            if job.kind == "tick":
                _maybe_run_gated_jobs(storage)
            elif job.kind == "backup":
                backup.run_backup(storage)
            else:
                run_job(job, storage)
        except Exception:
            import traceback

            traceback.print_exc()


def _scheduler(slow_queue: "queue.Queue", shutdown: threading.Event) -> None:
    while not shutdown.wait(SCHEDULER_INTERVAL_S):
        slow_queue.put(Job(kind="tick"))


class Handler(BaseHTTPRequestHandler):
    fast_queue: "queue.Queue" = None  # setado dinamicamente em main() via subclasse

    def log_message(self, fmt: str, *args) -> None:  # silencia o log padrão, print no formato do projeto
        print(f"[http] {self.address_string()} {fmt % args}", file=sys.stderr)

    def _reply(self, status: int, body: bytes = b"") -> None:
        self.send_response(status)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if body:
            self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path == "/healthz":
            self._reply(200, b"ok")
        else:
            self._reply(404)

    def do_POST(self) -> None:
        if self.path != WEBHOOK_PATH:
            self._reply(404)
            return
        secret = os.environ.get("TELEGRAM_WEBHOOK_SECRET", "")
        got = self.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
        if not secret or got != secret:  # sem secret configurada = nega tudo (fail closed)
            self._reply(401, b"unauthorized")
            return

        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b""
        # Responde 200 ANTES de processar: o Telegram reenvia com backoff se não
        # receber 200 rápido, e processar primeiro arriscaria timeout + reenvio
        # duplicado (o dedupe por update_id no worker cobre reenvios de qualquer jeito).
        self._reply(200, b"ok")

        try:
            update = json.loads(body) if body else {}
        except json.JSONDecodeError:
            return
        if update:
            self.fast_queue.put(update)


def main() -> None:
    fast_q: "queue.Queue" = queue.Queue()
    slow_q: "queue.Queue" = queue.Queue()
    shutdown = threading.Event()

    fast_t = threading.Thread(target=_fast_worker, args=(fast_q, slow_q), name="fast-worker")
    slow_t = threading.Thread(target=_slow_worker, args=(slow_q,), name="slow-worker")
    sched_t = threading.Thread(target=_scheduler, args=(slow_q, shutdown), name="scheduler")
    for t in (fast_t, slow_t, sched_t):
        t.start()

    handler_cls = type("WebhookHandler", (Handler,), {"fast_queue": fast_q})
    httpd = ThreadingHTTPServer(("0.0.0.0", PORT), handler_cls)  # 0.0.0.0 só dentro do container; sem `ports:` no compose

    def _stop(signum, _frame) -> None:
        print(f"[server] sinal {signum}, encerrando...", file=sys.stderr)
        shutdown.set()
        threading.Thread(target=httpd.shutdown, daemon=True).start()

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)

    print(f"[server] ouvindo em 0.0.0.0:{PORT}{WEBHOOK_PATH}", file=sys.stderr)
    httpd.serve_forever()

    print("[server] http parado; esperando os workers (até 25s cada)...", file=sys.stderr)
    fast_q.put(None)
    slow_q.put(None)
    fast_t.join(timeout=JOIN_TIMEOUT_S)
    slow_t.join(timeout=JOIN_TIMEOUT_S)
    sched_t.join(timeout=5)
    print("[server] encerrado.", file=sys.stderr)


if __name__ == "__main__":
    main()
