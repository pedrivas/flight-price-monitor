from __future__ import annotations

import html
from urllib.parse import urlencode

from .models import FlightLeg, Offer, RouteQuery
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


def format_duration(minutes: int) -> str:
    h, m = divmod(minutes, 60)
    return f"{h}h{m:02d}" if m else f"{h}h"


def format_leg(leg: FlightLeg) -> str:
    """'GRU –11h20→ LHR [conexão 1h50] –3h55→ IST · 23h05 no total'."""
    if leg.stops == 0:
        return f"{leg.airports[0]} → {leg.airports[-1]} · {format_duration(leg.total_minutes)} (direto)"
    bits = [leg.airports[0]]
    for i, seg_min in enumerate(leg.seg_minutes):
        bits.append(f"–{format_duration(seg_min)}→")
        bits.append(leg.airports[i + 1])
        if i < len(leg.layover_minutes):
            bits.append(f"[conexão {format_duration(leg.layover_minutes[i])}]")
    return " ".join(bits) + f" · {format_duration(leg.total_minutes)} no total"


def format_alert(route: RouteQuery, offer: Offer, decision: AlertDecision) -> str:
    trip = (
        f"📅 Ida {offer.depart_date} · Volta {offer.return_date}"
        if offer.return_date
        else f"📅 Ida {offer.depart_date} (só ida)"
    )
    lines = [
        f"✈️ <b>Promoção: {esc(route.name)}</b>",
        "",
        f"💰 <b>{esc(offer.currency)} {offer.price:,.0f}</b>  "
        f"({esc(', '.join(decision.reasons))})",
        trip,
        f"🛫 {esc(offer.carrier)} · {route.adults} pax",
    ]
    if offer.outbound:
        label = "🧭 Voo" if not offer.return_date else "🧭 Ida"
        lines.append(f"{label}: {esc(format_leg(offer.outbound))}")
        if offer.return_date:
            lines.append("   <i>(duração e conexão só do trecho de ida — a fonte não detalha a volta)</i>")
    else:
        stops = "direto" if offer.stops == 0 else f"{offer.stops} conexão(ões)"
        lines.append(f"🧭 {stops}")
    lines += ["", f"🔗 {google_flights_link(route, offer)}"]
    return "\n".join(lines)


class TelegramNotifier:
    """Wrapper fino sobre TelegramClient para o caminho de alerta."""

    def __init__(self, client: TelegramClient | None = None) -> None:
        self._client = client or TelegramClient()

    def send(self, text: str) -> None:
        self._client.send_message(text)
