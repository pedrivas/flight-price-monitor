from __future__ import annotations

from dataclasses import replace
from datetime import date

from conftest import make_offer

from monitor.models import FlightLeg
from monitor.notifier import format_alert, format_duration, format_leg, google_flights_link
from monitor.rules import AlertDecision

DECISION = AlertDecision(should_alert=True, reasons=["preço 850 ≤ alvo 900"], baseline=1000.0)

DIRECT_LEG = FlightLeg(airports=["GRU", "IST"], seg_minutes=[915], layover_minutes=[], total_minutes=915)
CONN_LEG = FlightLeg(
    airports=["GRU", "LHR", "IST"], seg_minutes=[680, 235], layover_minutes=[110], total_minutes=1385
)


def test_escapes_html_in_route_name(route):
    r = replace(route, name="GRU <-> REC & cia")
    msg = format_alert(r, make_offer(r, 850), DECISION)
    assert "&lt;-&gt;" in msg and "&amp; cia" in msg  # entrada escapada
    assert "<b>Promoção:" in msg                       # tags próprias preservadas


def test_roundtrip_shows_both_dates(route):
    msg = format_alert(route, make_offer(route, 850), DECISION)
    assert "Ida 2026-11-10" in msg and "Volta 2026-11-17" in msg


def test_oneway_omits_return(route):
    r = replace(route, return_after_days=None)
    offer = replace(make_offer(r, 850), return_date=None)
    msg = format_alert(r, offer, DECISION)
    assert "só ida" in msg and "Volta" not in msg


def test_google_link_has_route_and_dates(route):
    link = google_flights_link(route, make_offer(route, 850))
    assert link.startswith("https://www.google.com/travel/flights?")
    assert "GRU" in link and "REC" in link and "2026-11-10" in link


def test_format_duration():
    assert format_duration(915) == "15h15"
    assert format_duration(120) == "2h"
    assert format_duration(45) == "0h45"


def test_format_leg_direct():
    assert format_leg(DIRECT_LEG) == "GRU → IST · 15h15 (direto)"


def test_format_leg_with_connection():
    assert format_leg(CONN_LEG) == "GRU –11h20→ LHR [conexão 1h50] –3h55→ IST · 23h05 no total"


def test_alert_includes_direct_itinerary(route):
    offer = replace(make_offer(route, 850), outbound=DIRECT_LEG)
    msg = format_alert(route, offer, DECISION)
    assert "🧭 Ida: GRU → IST · 15h15 (direto)" in msg


def test_alert_includes_connection_and_ida_only_note(route):
    offer = replace(make_offer(route, 850), outbound=CONN_LEG)
    msg = format_alert(route, offer, DECISION)
    assert "LHR" in msg and "conexão 1h50" in msg
    assert "só do trecho de ida" in msg  # avisa que a volta não é detalhada


def test_oneway_itinerary_has_no_ida_only_note(route):
    r = replace(route, return_after_days=None)
    offer = replace(make_offer(r, 850), return_date=None, outbound=DIRECT_LEG)
    msg = format_alert(r, offer, DECISION)
    assert "🧭 Voo:" in msg
    assert "só do trecho de ida" not in msg


def test_alert_falls_back_without_outbound_detail(route):
    offer = make_offer(route, 850)  # outbound=None (fonte sem detalhe, ex.: travelpayouts)
    msg = format_alert(route, offer, DECISION)
    assert "🧭 direto" in msg
