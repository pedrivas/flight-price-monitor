from __future__ import annotations

from dataclasses import replace
from datetime import date

from conftest import link_has, make_offer, seed_route

from monitor.bot import Job, handle_message, run_job
from monitor.links import option_links, route_option_lines, sweep_summary


def _record(storage, route, price, key=None, dep=date(2027, 5, 26), ret=date(2027, 6, 14), carrier="Iberia"):
    storage.record(replace(make_offer(route, price), route_key=key or route.key,
                           depart_date=dep, return_date=ret, carrier=carrier))


def test_direct_link_is_round_trip_search():
    r = replace(seed_route_query(), origin="SAO", dest="ATH")
    [(label, url)] = option_links(r, r.key, date(2027, 5, 26), date(2027, 6, 14))
    assert label == "Google Flights"
    assert link_has(url, "2027-05-26", "SAO", "ATH", "2027-06-14", "ATH", "SAO")


def test_hub_links_follow_layover_rule():
    r = replace(seed_route_query(), origin="SAO", dest="ATH", hubs=["BCN"])
    (l1, u1), (l2, u2) = option_links(r, f"{r.key}@BCN", date(2027, 5, 26), date(2027, 6, 14))
    assert (l1, l2) == ("SAO⇄BCN", "BCN⇄ATH")
    assert link_has(u1, "2027-05-26", "SAO", "BCN", "2027-06-14", "BCN", "SAO")
    assert link_has(u2, "2027-05-28", "BCN", "ATH", "2027-06-12", "ATH", "BCN")  # 2 dias de folga de cada lado


def test_open_jaw_links_include_multi_city():
    r = replace(seed_route_query(), origin="SAO", dest="IST", return_from="ATH")
    links = option_links(r, r.key, date(2027, 5, 26), date(2027, 6, 14))
    assert [lbl for lbl, _ in links] == ["SAO→IST", "ATH→SAO", "multidestino"]
    assert link_has(links[1][1], "2027-06-14", "ATH", "SAO")
    assert link_has(links[2][1], "2027-05-26", "SAO", "IST", "2027-06-14", "ATH", "SAO")


def test_route_option_lines_one_per_priced_option(storage):
    r = storage.get_route(seed_route(storage, origin="SAO", dest="ATH", hubs="BCN,MAD"))
    _record(storage, r, 4712)
    _record(storage, r, 5000, key=f"{r.key}@BCN", carrier="Avianca + SKY express")
    lines = route_option_lines(storage, r)  # MAD sem preço ainda: fica de fora
    assert len(lines) == 2
    assert lines[0].startswith("direto: BRL 4712 · 26/05→14/06 · Iberia · 🔗 <a href=")
    assert lines[1].startswith("via BCN: BRL 5000") and ">SAO⇄BCN</a>" in lines[1]


def test_editar_id_shows_prices_dates_and_links(storage):
    r = storage.get_route(seed_route(storage, origin="SAO", dest="ATH", hubs="BCN"))
    _record(storage, r, 4712)
    out = handle_message(f"/editar {r.id}", storage)
    assert "últimos preços" in out and "💰 direto: BRL 4712 · 26/05→14/06" in out
    assert "via hub (2 passagens): BCN" in out


def test_sweep_summary_uses_cheapest_option(storage):
    r = storage.get_route(seed_route(storage, origin="SAO", dest="ATH", hubs="BCN", target_price=4650.0))
    seed_route(storage, name="Sem preço", dest="REC")
    _record(storage, r, 4712)
    _record(storage, r, 4600, key=f"{r.key}@BCN", carrier="Avianca + Vueling")
    text = sweep_summary(storage, alerts=1)
    assert "Varredura concluída</b> · 2 monitoria(s) · 1 alerta(s)" in text
    assert "alvo 4650" in text and "via BCN: BRL 4600" in text and ">BCN⇄ATH</a>" in text
    assert "sem preço nesta varredura" in text


def test_varrer_job_sends_summary(storage, monkeypatch, fake_telegram):
    import monitor.bot as bot_mod

    seed_route(storage)
    monkeypatch.setattr("monitor.main.run_sweep", lambda *a, **k: 0)
    monkeypatch.setattr(bot_mod, "TelegramClient", lambda: fake_telegram)
    run_job(Job(kind="sweep"), storage)
    assert storage.kv_get("last_sweep_at")
    assert "Varredura concluída" in fake_telegram.sent[0][1]


def seed_route_query():
    from monitor.models import RouteQuery

    return RouteQuery(id=14, name="r", origin="SAO", dest="ATH",
                      depart_range=(date(2027, 5, 26), date(2027, 5, 31)), return_after_days=(14, 19))


def test_links_are_prefilled_searches_not_text_queries():
    # ?q=Flights from X to Y abre o Google Flights vazio — todo link tem que ser tfs
    r = replace(seed_route_query(), origin="SAO", dest="ATH", hubs=["MXP"])
    for _, url in option_links(r, f"{r.key}@MXP", date(2027, 5, 31), date(2027, 6, 14)):
        assert "tfs=" in url and "?q=" not in url
