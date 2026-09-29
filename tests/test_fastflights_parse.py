from __future__ import annotations

import pytest
from fast_flights.exceptions import FlightsNotFound

from monitor.sources.fastflights import parse_html, parse_payload


def _sf(frm, to, day, dep, arr, minutes):
    """Segmento no formato cru do Google (só os índices que o parser lê)."""
    sf = [None] * 22
    sf[3], sf[4], sf[5], sf[6] = frm, f"{frm} airport", f"{to} airport", to
    sf[8], sf[10], sf[11], sf[17] = dep, arr, minutes, "A330"
    sf[20], sf[21] = [2027, 4, day], [2027, 4, day + 1]
    return sf


def _item(price, airlines, *segments):
    return [["type", airlines, list(segments)], [[None, price]]]


def _payload(best=None, other=None):
    p = [None] * 8  # payload[7] (alianças/companhias) ausente, como na resposta multidestino
    p[2] = [best] if best is not None else None
    p[3] = [other] if other is not None else None
    return p


KLM = _item(6171, ["KLM"], _sf("GRU", "AMS", 5, [18, 5], [10, 40], 695), _sf("AMS", "IST", 6, [12], [16, 50], 230))
LH = _item(6863, ["Lufthansa"], _sf("GRU", "FRA", 5, [17, 30], [9, 50], 700))


def test_reads_best_flights_block():
    # o parser da lib só olhava o bloco 3 e perdia o KLM, R$ 700 mais barato
    flights = parse_payload(_payload(best=[KLM], other=[LH]))
    assert sorted(f.price for f in flights) == [6171, 6863]
    klm = next(f for f in flights if f.price == 6171)
    assert [s.to_airport.code for s in klm.flights] == ["AMS", "IST"]
    assert klm.flights[1].departure.time == (12, 0)  # [12] = 12:00


def test_dedupes_flight_present_in_both_blocks():
    assert len(parse_payload(_payload(best=[KLM], other=[KLM, LH]))) == 2


def test_skips_malformed_item_keeps_rest():
    assert [f.price for f in parse_payload(_payload(other=[["lixo"], LH]))] == [6863]


def test_empty_blocks():
    assert parse_payload(_payload()) == []


def test_parse_html_error_status():
    html = '<script class="ds:1">AF_initDataCallback({data: errorHasStatus: true, x});</script>'
    with pytest.raises(FlightsNotFound):
        parse_html(html)
