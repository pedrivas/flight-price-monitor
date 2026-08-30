from __future__ import annotations

import os
from urllib.parse import urlencode

import requests

from .models import Offer, RouteQuery
from .rules import AlertDecision


def google_flights_link(route: RouteQuery, offer: Offer) -> str:
    q = f"Flights from {route.origin} to {route.dest} on {offer.depart_date}"
    if offer.return_date:
        q += f" returning {offer.return_date}"
    return "https://www.google.com/travel/flights?" + urlencode({"q": q})


def format_alert(route: RouteQuery, offer: Offer, decision: AlertDecision) -> str:
    stops = "direto" if offer.stops == 0 else f"{offer.stops} conexão(ões)"
    lines = [
        f"✈️ *Promoção: {route.name}*",
        "",
        f"💰 *{offer.currency} {offer.price:,.0f}*  ({', '.join(decision.reasons)})",
        f"📅 Ida {offer.depart_date}" + (f" · Volta {offer.return_date}" if offer.return_date else " (só ida)"),
        f"🛫 {offer.carrier} · {stops} · {route.adults} pax",
        "",
        f"🔗 {google_flights_link(route, offer)}",
    ]
    return "\n".join(lines)


class TelegramNotifier:
    def __init__(self) -> None:
        self.token = os.environ["TELEGRAM_BOT_TOKEN"]
        self.chat_id = os.environ["TELEGRAM_CHAT_ID"]

    def send(self, text: str) -> None:
        resp = requests.post(
            f"https://api.telegram.org/bot{self.token}/sendMessage",
            json={
                "chat_id": self.chat_id,
                "text": text,
                "parse_mode": "Markdown",
                "disable_web_page_preview": False,
            },
            timeout=20,
        )
        resp.raise_for_status()
