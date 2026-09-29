from __future__ import annotations

import html
from urllib.parse import urlencode

from .airports import city_country
from .models import FlightLeg, Offer, RouteQuery
from .rules import AlertDecision
from .telegram import TelegramClient


def esc(value: object) -> str:
    """Escapa texto para o parse_mode HTML do Telegram."""
    return html.escape(str(value), quote=False)


# alias interno mantido por compatibilidade
_esc = esc


def _flights_link(origin: str, dest: str, depart, return_date=None) -> str:
    q = f"Flights from {origin} to {dest} on {depart}"
    if return_date:
        q += f" returning {return_date}"
    return "https://www.google.com/travel/flights?" + urlencode({"q": q})


def google_flights_link(route: RouteQuery, offer: Offer) -> str:
    return _flights_link(route.origin, route.dest, offer.depart_date, offer.return_date)


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


def _format_split_alert(route: RouteQuery, offer: Offer, decision: AlertDecision,
                        direct_price: float | None) -> str:
    """Alerta de uma oferta via hub: um bloco por bilhete, comparação com o
    direto e o aviso de passagens separadas (ADR-009)."""
    hub_city, _ = city_country(offer.via or "")
    round_trip = offer.return_date is not None
    arrow = "⇄" if round_trip else "→"
    lines = [
        f"✈️ <b>Promoção: {esc(route.name)}</b> — via {esc(hub_city)} (2 passagens)",
        "",
        f"💰 <b>{esc(offer.currency)} {offer.price:,.0f} no total</b>  "
        f"({esc(', '.join(decision.reasons))})",
    ]
    if direct_price is not None:
        lines.append(f"   direto hoje: {esc(offer.currency)} {direct_price:,.0f}")
    links = []
    for i, leg in enumerate(offer.legs, start=1):
        o, d = leg.origin or "?", leg.dest or "?"
        dates = f"ida {leg.depart_date:%d/%m}" + (f" · volta {leg.return_date:%d/%m}" if leg.return_date else "")
        lines.append(
            f"🎫 {i}) {esc(o)}{arrow}{esc(d)} · {dates} · {esc(leg.carrier)} · "
            f"{esc(leg.currency)} {leg.price:,.0f}"
        )
        if leg.outbound:
            lines.append(f"   🧭 {esc(format_leg(leg.outbound))}")
        links.append(f"{i}) {_flights_link(o, d, leg.depart_date, leg.return_date)}")
    lines += [
        f"⚠️ <i>Passagens separadas: atraso no 1º trecho não garante o 2º "
        f"(há 2 dias de folga no hub). Bagagem é cobrada em cada bilhete.</i>",
        "",
        "🔗 " + "\n🔗 ".join(links),
    ]
    return "\n".join(lines)


def format_alert(route: RouteQuery, offer: Offer, decision: AlertDecision,
                 direct_price: float | None = None) -> str:
    if offer.legs:
        return _format_split_alert(route, offer, decision, direct_price)
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
