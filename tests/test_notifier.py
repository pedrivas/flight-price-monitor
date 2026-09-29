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


def test_split_alert_lists_each_ticket_and_warns(route):
    outer = replace(make_offer(route, 2400), origin="SAO", dest="LIS", carrier="Azul", outbound=DIRECT_LEG)
    inner = replace(make_offer(route, 600), origin="LIS", dest="ATH", carrier="Aegean",
                    depart_date=date(2026, 11, 12), return_date=date(2026, 11, 15))
    via = replace(make_offer(route, 3000), via="LIS", legs=[outer, inner], route_key=f"{route.key}@LIS")
    msg = format_alert(route, via, DECISION, direct_price=3800)
    assert "via Lisboa (2 passagens)" in msg
    assert "3,000 no total" in msg and "direto hoje: BRL 3,800" in msg
    assert "1) SAO⇄LIS" in msg and "2) LIS⇄ATH · ida 12/11 · volta 15/11 · Aegean" in msg
    assert "Passagens separadas" in msg and "Bagagem" in msg
    assert msg.count("🔗") == 2 and "from+LIS+to+ATH+on+2026-11-12" in msg  # um link por bilhete


def test_open_jaw_alert_titles_legs_and_multi_city_link(route):
    out = replace(make_offer(route, 4245), origin="SAO", dest="IST", return_date=None, carrier="Air Europa")
    back = replace(make_offer(route, 2358), origin="ATH", dest="SAO", return_date=None, carrier="Air France",
                   depart_date=date(2026, 11, 22))
    oj = replace(make_offer(route, 6603), legs=[out, back], origin="SAO", dest="IST",
                 return_date=date(2026, 11, 22))
    msg = format_alert(route, oj, DECISION)
    assert "chega em Istambul, volta de Atenas (2 passagens só de ida)" in msg
    assert "1) SAO→IST · ida 10/11 · Air Europa" in msg and "2) ATH→SAO · ida 22/11 · Air France" in msg
    assert "trecho IST→ATH é por sua conta" in msg and "direto hoje" not in msg
    assert "multidestino (1 bilhete) https://www.google.com/travel/flights?tfs=" in msg
