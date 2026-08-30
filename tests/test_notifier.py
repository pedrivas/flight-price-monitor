from __future__ import annotations

from dataclasses import replace
from datetime import date

from conftest import make_offer

from monitor.notifier import format_alert, google_flights_link
from monitor.rules import AlertDecision

DECISION = AlertDecision(should_alert=True, reasons=["preço 850 ≤ alvo 900"], baseline=1000.0)


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
