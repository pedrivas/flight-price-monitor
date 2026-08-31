from __future__ import annotations

from datetime import date

import pytest

from monitor.models import Offer, RouteQuery
from monitor.storage import Storage


@pytest.fixture(autouse=True)
def _hermetic_env(monkeypatch):
    """Tests never touch a real .env or real Telegram credentials."""
    monkeypatch.setattr("monitor.main.load_dotenv", lambda *a, **k: None)
    monkeypatch.setattr("monitor.explore.load_dotenv", lambda *a, **k: None)
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    monkeypatch.delenv("TELEGRAM_ALLOWED_CHAT_IDS", raising=False)


@pytest.fixture
def storage(tmp_path) -> Storage:
    return Storage(tmp_path / "history.db")


class FakeTelegram:
    """Substitui TelegramClient nos testes do bot."""

    def __init__(self) -> None:
        self.sent: list[tuple[object, str]] = []
        self._updates: list[dict] = []

    def queue(self, update_id: int, text: str, chat_id: int = 1) -> None:
        self._updates.append(
            {"update_id": update_id, "message": {"text": text, "chat": {"id": chat_id}}}
        )

    def get_updates(self, offset: int | None = None, timeout: int = 0) -> list[dict]:
        if offset is None:
            return list(self._updates)
        return [u for u in self._updates if u["update_id"] >= offset]

    def send_message(self, text: str, chat_id=None) -> None:
        self.sent.append((chat_id, text))


@pytest.fixture
def fake_telegram() -> FakeTelegram:
    return FakeTelegram()


def seed_route(storage: Storage, **overrides) -> int:
    fields = dict(
        name="Rota teste", origin="GRU", dest="REC",
        depart_from="2026-11-05", depart_to="2026-11-20",
        return_min=5, return_max=9, adults=1,
        target_price=999999.0, drop_pct=20.0, nonstop=0, currency="BRL", active=1,
    )
    fields.update(overrides)
    return storage.add_route(**fields)


@pytest.fixture
def route() -> RouteQuery:
    return RouteQuery(
        name="Teste GRU-REC",
        origin="GRU",
        dest="REC",
        depart_range=(date(2026, 11, 5), date(2026, 11, 20)),
        adults=1,
        return_after_days=(5, 9),
        target_price=900.0,
        drop_pct=20.0,
    )


def make_offer(route: RouteQuery, price: float) -> Offer:
    return Offer(
        route_key=route.key,
        price=price,
        currency=route.currency,
        depart_date=date(2026, 11, 10),
        return_date=date(2026, 11, 17),
        carrier="LATAM",
        stops=0,
    )
