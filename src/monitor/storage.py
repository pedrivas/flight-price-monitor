from __future__ import annotations

import math
import os
import sqlite3
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from .models import Offer, RouteQuery

DB_PATH = Path(__file__).resolve().parents[2] / "data" / "history.db"


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")


SCHEMA = """
CREATE TABLE IF NOT EXISTS price_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    route_key   TEXT NOT NULL,
    price       REAL NOT NULL,
    currency    TEXT NOT NULL,
    depart_date TEXT NOT NULL,
    return_date TEXT,
    carrier     TEXT,
    stops       INTEGER,
    seen_at     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_hist_route ON price_history(route_key, seen_at);

CREATE TABLE IF NOT EXISTS alerts_sent (
    route_key  TEXT NOT NULL,
    price      REAL NOT NULL,
    sent_at    TEXT NOT NULL,
    PRIMARY KEY (route_key, price)
);

CREATE TABLE IF NOT EXISTS routes (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    name         TEXT NOT NULL,
    origin       TEXT NOT NULL,
    dest         TEXT NOT NULL,
    depart_from  TEXT NOT NULL,
    depart_to    TEXT NOT NULL,
    return_min   INTEGER,
    return_max   INTEGER,
    adults       INTEGER NOT NULL DEFAULT 1,
    target_price REAL,
    drop_pct     REAL,
    nonstop      INTEGER NOT NULL DEFAULT 0,
    currency     TEXT NOT NULL DEFAULT 'BRL',
    active       INTEGER NOT NULL DEFAULT 1,
    created_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS kv (k TEXT PRIMARY KEY, v TEXT NOT NULL);
"""

ROUTE_COLUMNS = (
    "name", "origin", "dest", "depart_from", "depart_to", "return_min", "return_max",
    "adults", "target_price", "drop_pct", "nonstop", "currency", "active",
)


class Storage:
    def __init__(self, path: Path | None = None) -> None:
        path = path or Path(os.environ.get("MONITOR_DB_PATH", DB_PATH))
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    # --- histórico de preços ------------------------------------------------
    def record(self, offer: Offer) -> None:
        self.conn.execute(
            """INSERT INTO price_history
               (route_key, price, currency, depart_date, return_date, carrier, stops, seen_at)
               VALUES (?,?,?,?,?,?,?,?)""",
            (
                offer.route_key,
                offer.price,
                offer.currency,
                offer.depart_date.isoformat(),
                offer.return_date.isoformat() if offer.return_date else None,
                offer.carrier,
                offer.stops,
                _utc_now(),
            ),
        )
        self.conn.commit()

    def last_price(self, route_key: str) -> float | None:
        row = self.conn.execute(
            "SELECT price FROM price_history WHERE route_key=? ORDER BY seen_at DESC LIMIT 1",
            (route_key,),
        ).fetchone()
        return row[0] if row else None

    def median_last_days(self, route_key: str, days: int = 30) -> float | None:
        since = (date.today() - timedelta(days=days)).isoformat()
        rows = self.conn.execute(
            "SELECT price FROM price_history WHERE route_key=? AND seen_at>=? ORDER BY price",
            (route_key, since),
        ).fetchall()
        if not rows:
            return None
        prices = [r[0] for r in rows]
        mid = len(prices) // 2
        return prices[mid] if len(prices) % 2 else (prices[mid - 1] + prices[mid]) / 2

    def already_alerted(self, route_key: str, price: float, tolerance: float = 0.02) -> bool:
        """Evita reenviar a mesma promoção. Considera preços dentro de `tolerance`
        (2%) como 'o mesmo alerta'."""
        rows = self.conn.execute(
            "SELECT price FROM alerts_sent WHERE route_key=? AND sent_at>=?",
            (route_key, (date.today() - timedelta(days=7)).isoformat()),
        ).fetchall()
        return any(abs(p[0] - price) <= p[0] * tolerance for p in rows)

    def mark_alerted(self, route_key: str, price: float) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO alerts_sent (route_key, price, sent_at) VALUES (?,?,?)",
            (route_key, price, _utc_now()),
        )
        self.conn.commit()

    # --- rotas ------------------------------------------------------------
    def list_routes(self, active_only: bool = True) -> list[RouteQuery]:
        sql = "SELECT * FROM routes"
        if active_only:
            sql += " WHERE active=1"
        sql += " ORDER BY id"
        return [_row_to_route(r) for r in self.conn.execute(sql).fetchall()]

    def get_route(self, route_id: int) -> RouteQuery | None:
        row = self.conn.execute("SELECT * FROM routes WHERE id=?", (route_id,)).fetchone()
        return _row_to_route(row) if row else None

    def add_route(self, **fields) -> int:
        cols = [c for c in ROUTE_COLUMNS if c in fields]
        placeholders = ", ".join("?" for _ in cols)
        cur = self.conn.execute(
            f"INSERT INTO routes ({', '.join(cols)}, created_at) "
            f"VALUES ({placeholders}, ?)",
            [fields[c] for c in cols] + [_utc_now()],
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def update_route(self, route_id: int, **fields) -> bool:
        cols = [c for c in ROUTE_COLUMNS if c in fields]
        if not cols:
            return False
        assignments = ", ".join(f"{c}=?" for c in cols)
        cur = self.conn.execute(
            f"UPDATE routes SET {assignments} WHERE id=?",
            [fields[c] for c in cols] + [route_id],
        )
        self.conn.commit()
        return cur.rowcount > 0

    def set_route_active(self, route_id: int, active: bool) -> bool:
        cur = self.conn.execute(
            "UPDATE routes SET active=? WHERE id=?", (1 if active else 0, route_id)
        )
        self.conn.commit()
        return cur.rowcount > 0

    def seed_routes(self, routes: list[RouteQuery]) -> int:
        """Popula a tabela `routes` a partir de uma lista (só se estiver vazia)."""
        if self.conn.execute("SELECT 1 FROM routes LIMIT 1").fetchone():
            return 0
        for r in routes:
            lo, hi = r.return_after_days or (None, None)
            self.add_route(
                name=r.name, origin=r.origin, dest=r.dest,
                depart_from=r.depart_range[0].isoformat(),
                depart_to=r.depart_range[1].isoformat(),
                return_min=lo, return_max=hi, adults=r.adults,
                target_price=r.target_price, drop_pct=r.drop_pct,
                nonstop=1 if r.nonstop else 0, currency=r.currency, active=1,
            )
        return len(routes)

    # --- kv / agendamento ------------------------------------------------
    def kv_get(self, k: str) -> str | None:
        row = self.conn.execute("SELECT v FROM kv WHERE k=?", (k,)).fetchone()
        return row[0] if row else None

    def kv_set(self, k: str, v: str) -> None:
        self.conn.execute("INSERT OR REPLACE INTO kv (k, v) VALUES (?, ?)", (k, str(v)))
        self.conn.commit()

    def hours_since_last_sweep(self) -> float:
        raw = self.kv_get("last_sweep_at")
        if not raw:
            return math.inf
        last = datetime.strptime(raw, "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - last).total_seconds() / 3600

    def mark_sweep_done(self) -> None:
        self.kv_set("last_sweep_at", _utc_now())


def _row_to_route(row: sqlite3.Row) -> RouteQuery:
    rad = None
    if row["return_min"] is not None:
        rad = (int(row["return_min"]), int(row["return_max"]))
    return RouteQuery(
        id=row["id"],
        name=row["name"],
        origin=row["origin"],
        dest=row["dest"],
        depart_range=(date.fromisoformat(row["depart_from"]), date.fromisoformat(row["depart_to"])),
        adults=int(row["adults"]),
        return_after_days=rad,
        target_price=row["target_price"],
        drop_pct=row["drop_pct"],
        nonstop=bool(row["nonstop"]),
        currency=row["currency"],
        active=bool(row["active"]),
    )
