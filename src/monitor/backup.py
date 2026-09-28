"""Backup diário do SQLite pro OCI Object Storage via Pre-Authenticated Request
(PAR) de escrita — sem OCI CLI, sem chave de API, sem dependência nova: é só
um PUT autenticado pela própria URL.

Falha de backup só loga e nunca derruba o processo, mesma filosofia do resto
do projeto (ex.: `main.run_sweep` com o envio do Telegram) — um provedor de
terceiros instável não pode travar o monitor.
"""
from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path

import requests

from .storage import Storage

BACKUP_INTERVAL_H = 24


def hours_since_last_backup(storage: Storage) -> float:
    raw = storage.kv_get("last_backup_at")
    if not raw:
        return float("inf")
    last = datetime.strptime(raw, "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - last).total_seconds() / 3600


def mark_backup_done(storage: Storage) -> None:
    storage.kv_set("last_backup_at", datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"))


def run_backup(storage: Storage) -> bool:
    """Faz o backup e marca o gate. Devolve True se enviou; False se pulou
    (sem PAR configurada) ou falhou — nesses casos o gate também é marcado,
    pra não tentar de novo a cada tick do scheduler (1/min)."""
    par_url = os.environ.get("OCI_BACKUP_PAR_URL")
    if not par_url:
        print("[backup] OCI_BACKUP_PAR_URL não configurada — pulando por 24h", file=sys.stderr)
        mark_backup_done(storage)
        return False

    name = f"history-{date.today().isoformat()}.db"
    try:
        with tempfile.TemporaryDirectory() as tmp:
            snapshot = Path(tmp) / "history.db"
            # sqlite3.Connection.backup() tira um snapshot consistente mesmo com
            # o WAL ativo e escritas concorrentes — copiar o arquivo na unha não
            # teria essa garantia.
            dst = sqlite3.connect(snapshot)
            try:
                storage.conn.backup(dst)
            finally:
                dst.close()

            url = par_url.rstrip("/") + "/" + name
            with open(snapshot, "rb") as fh:
                resp = requests.put(url, data=fh, timeout=60)
            resp.raise_for_status()
        print(f"[backup] enviado: {name}", file=sys.stderr)
        mark_backup_done(storage)
        return True
    except Exception as exc:
        print(f"[backup] falhou, não derruba o processo ({name}): {exc}", file=sys.stderr)
        mark_backup_done(storage)
        return False
