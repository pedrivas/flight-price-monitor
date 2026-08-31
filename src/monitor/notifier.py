from __future__ import annotations

import html
from urllib.parse import urlencode

from .models import Offer, RouteQuery
from .rules import AlertDecision
from .telegram import TelegramClient


def esc(value: object) -> str:
    """Escapa texto para o parse_mode HTML do Telegram."""
    return html.escape(str(value), quote=False)


# alias interno mantido por compatibilidade
_esc = esc


def google_flights_link(route: RouteQuery, offer: Offer) -> str:
    q = f"Flights from {route.origin} to {route.dest} on {offer.depart_date}"
    if offer.return_date:
        q += f" returning {offer.return_date}"
    return "https://www.google.com/travel/flights?" + urlencode({"q": q})


def format_alert(route: RouteQuery, offer: Offer, decision: AlertDecision) -> str:
    stops = "direto" if offer.stops == 0 else f"{offer.stops} conexão(ões)"
    trip = (
        f"📅 Ida {offer.depart_date} · Volta {offer.return_date}"
        if offer.return_date
        else f"📅 Ida {offer.depart_date} (só ida)"
    )
    return "\n".join(
        [
            f"✈️ <b>Promoção: {esc(route.name)}</b>",
            "",
            f"💰 <b>{esc(offer.currency)} {offer.price:,.0f}</b>  "
            f"({esc(', '.join(decision.reasons))})",
            trip,
            f"🛫 {esc(offer.carrier)} · {stops} · {route.adults} pax",
            "",
            f"🔗 {google_flights_link(route, offer)}",
        ]
    )


class TelegramNotifier:
    """Wrapper fino sobre TelegramClient para o caminho de alerta."""

    def __init__(self, client: TelegramClient | None = None) -> None:
        self._client = client or TelegramClient()

    def send(self, text: str) -> None:
        self._client.send_message(text)
