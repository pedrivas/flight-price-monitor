from __future__ import annotations

import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path

from .models import Offer

DB_PATH = Path(__file__).resolve().parents[2] / "data" / "history.db"

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
"""


class Storage:
    def __init__(self, path: Path = DB_PATH) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path)
        self.conn.executescript(SCHEMA)
        self.conn.commit()

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
                datetime.utcnow().isoformat(timespec="seconds"),
            ),
        )
        self.conn.commit()

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
            (route_key, price, datetime.utcnow().isoformat(timespec="seconds")),
        )
        self.conn.commit()
