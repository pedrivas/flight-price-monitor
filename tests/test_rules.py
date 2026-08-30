from __future__ import annotations

from dataclasses import replace

from conftest import make_offer

from monitor.rules import evaluate


def test_target_price_hit(storage, route):
    decision = evaluate(route, make_offer(route, 850), storage)
    assert decision.should_alert
    assert any("alvo" in r for r in decision.reasons)


def test_target_price_miss_no_history(storage, route):
    decision = evaluate(route, make_offer(route, 950), storage)
    assert not decision.should_alert
    assert decision.reasons == []


def test_drop_rule_needs_history(storage, route):
    # sem histórico o drop_pct não pode ser avaliado
    r = replace(route, target_price=None)
    decision = evaluate(r, make_offer(r, 950), storage)
    assert not decision.should_alert
    assert decision.baseline is None


def test_drop_rule_fires_against_baseline(storage, route):
    r = replace(route, target_price=None)  # isola a regra de queda
    for p in (2000, 2000, 2000):
        storage.record(make_offer(r, p))
    decision = evaluate(r, make_offer(r, 1500), storage)  # -25% vs mediana 2000
    assert decision.should_alert
    assert any("queda" in x for x in decision.reasons)


def test_drop_rule_below_threshold_does_not_fire(storage, route):
    r = replace(route, target_price=None)
    for p in (2000, 2000, 2000):
        storage.record(make_offer(r, p))
    decision = evaluate(r, make_offer(r, 1700), storage)  # -15%, limiar é -20%
    assert not decision.should_alert


def test_dedupe_suppresses_repeat_alert(storage, route):
    offer = make_offer(route, 850)
    first = evaluate(route, offer, storage)
    assert first.should_alert
    storage.mark_alerted(offer.route_key, offer.price)

    second = evaluate(route, make_offer(route, 845), storage)  # dentro de 2%
    assert not second.should_alert
    assert "alertado" in second.reasons[0]


def test_both_reasons_when_target_and_drop_hit(storage, route):
    for p in (2000, 2000, 2000):
        storage.record(make_offer(route, p))
    decision = evaluate(route, make_offer(route, 800), storage)
    assert decision.should_alert
    assert len(decision.reasons) == 2
