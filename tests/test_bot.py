from __future__ import annotations

from conftest import seed_route

from monitor.bot import Job, dispatch_message, handle_message, handle_update, poll_and_handle


# --- handle_message: comandos individuais ---------------------------------
def test_help(storage):
    assert "Comandos" in handle_message("/help", storage)
    assert "Comandos" in handle_message("/start@meu_bot", storage)


def test_list_empty(storage):
    assert "Nenhuma monitoria" in handle_message("/monitorias", storage)


def test_list_shows_routes(storage):
    seed_route(storage, name="GRU→BEL", dest="BEL", target_price=1700.0)
    out = handle_message("/monitorias", storage)
    assert "BEL" in out and "Brasil" in out and "1700" in out


def test_list_table_has_header_and_alignment(storage):
    seed_route(storage, dest="CAI", target_price=5800.0)
    out = handle_message("/monitorias", storage)
    assert "<pre>" in out and "</pre>" in out
    assert "Dest" in out and "País" in out and "Egito" in out


def test_list_table_stays_narrow_for_mobile(storage):
    # bloco <pre> largo demais quebra linha (e o alinhamento junto) no app
    # mobile do Telegram, que não rola de lado como o desktop
    seed_route(storage, dest="MNL", target_price=6800.0)  # Filipinas: país mais longo do mapa
    out = handle_message("/monitorias", storage)
    pre_body = out.split("<pre>")[1].split("</pre>")[0]
    widest_line = max(len(line) for line in pre_body.splitlines())
    assert widest_line <= 32


def test_criar_roundtrip(storage):
    out = handle_message("/criar GRU BEL 2026-09-04..2026-09-11 7-21 1700 15", storage)
    assert "#1" in out and "criada" in out
    r = storage.list_routes()[0]
    assert r.origin == "GRU" and r.dest == "BEL"
    assert r.depart_range[0].isoformat() == "2026-09-04"
    assert r.return_after_days == (7, 21)
    assert r.target_price == 1700 and r.drop_pct == 15


def test_criar_one_way(storage):
    handle_message("/criar GRU BEL 2026-09-04..2026-09-11 - 1700", storage)
    assert storage.list_routes()[0].return_after_days is None


def test_criar_with_flags(storage):
    handle_message("/criar GRU BEL 2026-09-04..2026-09-11 7-21 1700 --nonstop --pax 2", storage)
    r = storage.list_routes()[0]
    assert r.nonstop is True and r.adults == 2


def test_criar_rejects_bad_airport(storage):
    assert "aeroporto" in handle_message("/criar SAOPAULO BEL 2026-09-04..2026-09-11 7-21 1700", storage)


def test_criar_rejects_bad_date(storage):
    assert "data inválida" in handle_message("/criar GRU BEL 2026-13-04..2026-09-11 7-21 1700", storage)


def test_criar_requires_a_criterion(storage):
    assert "ALVO ou DROP" in handle_message("/criar GRU BEL 2026-09-04..2026-09-11 7-21 -", storage)


def test_editar_target(storage):
    seed_route(storage)
    out = handle_message("/editar 1 alvo 1600", storage)
    assert "atualizada" in out
    assert storage.get_route(1).target_price == 1600


def test_editar_name_with_spaces(storage):
    seed_route(storage)
    handle_message("/editar 1 nome São Paulo → Belém", storage)
    assert storage.get_route(1).name == "São Paulo → Belém"


def test_editar_nights_to_one_way(storage):
    seed_route(storage)
    handle_message("/editar 1 noites -", storage)
    assert storage.get_route(1).return_after_days is None


def test_editar_unknown_route(storage):
    assert "não existe" in handle_message("/editar 9 alvo 1000", storage)


def test_editar_unknown_field(storage):
    seed_route(storage)
    assert "campo desconhecido" in handle_message("/editar 1 xpto 5", storage)


def test_excluir_needs_confirmation(storage):
    seed_route(storage)
    out = handle_message("/excluir 1", storage)
    assert "Confirme" in out
    assert storage.get_route(1).active is True


def test_excluir_confirmed(storage):
    seed_route(storage)
    handle_message("/excluir 1 sim", storage)
    assert storage.get_route(1).active is False
    assert storage.list_routes() == []


def test_unknown_command(storage):
    assert "desconhecido" in handle_message("/foobar", storage)


# --- poll_and_handle -----------------------------------------------------
def test_poll_creates_route_and_replies(storage, fake_telegram, monkeypatch):
    monkeypatch.setenv("TELEGRAM_ALLOWED_CHAT_IDS", "1")
    fake_telegram.queue(10, "/criar GRU BEL 2026-09-04..2026-09-11 7-21 1700", chat_id=1)

    n = poll_and_handle(storage, fake_telegram)

    assert n == 1
    assert len(storage.list_routes()) == 1
    assert "criada" in fake_telegram.sent[0][1]
    assert storage.kv_get("telegram_offset") == "10"


def test_poll_ignores_disallowed_chat(storage, fake_telegram, monkeypatch):
    monkeypatch.setenv("TELEGRAM_ALLOWED_CHAT_IDS", "1")
    fake_telegram.queue(5, "/criar GRU BEL 2026-09-04..2026-09-11 7-21 1700", chat_id=999)

    n = poll_and_handle(storage, fake_telegram)

    assert n == 0
    assert storage.list_routes() == []
    assert storage.kv_get("telegram_offset") == "5"  # avança mesmo assim


def test_poll_advances_offset_across_calls(storage, fake_telegram, monkeypatch):
    monkeypatch.setenv("TELEGRAM_ALLOWED_CHAT_IDS", "1")
    fake_telegram.queue(1, "/monitorias", chat_id=1)
    poll_and_handle(storage, fake_telegram)
    fake_telegram.queue(2, "/monitorias", chat_id=1)
    poll_and_handle(storage, fake_telegram)
    # a 2ª chamada só processa o update 2 → 2 respostas no total
    assert len(fake_telegram.sent) == 2
    assert storage.kv_get("telegram_offset") == "2"


# --- dispatch_message / Job (webhook) --------------------------------------
def test_dispatch_explore_returns_job(storage):
    reply, job = dispatch_message(
        "/explorar GRU 2026-10-01..2026-10-08 2026-10-15..2026-10-22 1800", storage
    )
    assert "rodando" in reply.lower()
    assert isinstance(job, Job) and job.kind == "explore"
    assert job.payload["origin"] == "GRU"
    assert job.payload["max_price"] == 1800


def test_dispatch_explore_with_destinations(storage):
    _reply, job = dispatch_message(
        "/explorar GRU 2026-10-01..2026-10-08 2026-10-15..2026-10-22 1800 REC,SSA", storage
    )
    assert job.payload["destinations"] == "REC,SSA"


def test_dispatch_explore_rejects_malformed_range(storage):
    reply, job = dispatch_message(
        "/explorar GRU 2026-10-01 2026-10-15..2026-10-22 1800", storage
    )
    assert job is None
    assert "AAAA-MM-DD" in reply


def test_dispatch_explore_rejects_missing_args(storage):
    reply, job = dispatch_message("/explorar GRU", storage)
    assert job is None and "uso:" in reply


def test_dispatch_varrer_returns_job(storage):
    reply, job = dispatch_message("/varrer", storage)
    assert isinstance(job, Job) and job.kind == "sweep"
    assert "varredura" in reply.lower()


def test_handle_message_drops_job_stays_pure(storage):
    # handle_message continua devolvendo só o texto — o Job não vaza pra quem
    # só quer a resposta síncrona (compat com os testes/usos antigos).
    reply = handle_message("/varrer", storage)
    assert "varredura" in reply.lower()


def test_handle_update_runs_job_inline_when_no_on_job(storage, fake_telegram, monkeypatch):
    calls = []
    monkeypatch.setattr("monitor.bot.run_job", lambda job, s: calls.append(job.kind))
    update = {"message": {"text": "/varrer", "chat": {"id": 1}}}

    handled = handle_update(update, storage, fake_telegram, allowed=set())

    assert handled is True
    assert calls == ["sweep"]
    assert len(fake_telegram.sent) == 1


def test_handle_update_forwards_job_via_on_job(storage, fake_telegram):
    received = []
    update = {"message": {"text": "/varrer", "chat": {"id": 1}}}

    handle_update(update, storage, fake_telegram, allowed=set(), on_job=received.append)

    assert len(received) == 1 and received[0].kind == "sweep"


def test_handle_update_respects_allowlist(storage, fake_telegram):
    update = {"message": {"text": "/monitorias", "chat": {"id": 999}}}

    handled = handle_update(update, storage, fake_telegram, allowed={1})

    assert handled is False
    assert fake_telegram.sent == []


def test_handle_update_ignores_non_text_update(storage, fake_telegram):
    assert handle_update({"message": {"chat": {"id": 1}}}, storage, fake_telegram, allowed=set()) is False


# --- hubs ------------------------------------------------------------------
def test_criar_with_explicit_hubs(storage):
    out, job = dispatch_message("/criar GRU ATH 2027-04-01..2027-04-30 10-15 3500 --hubs lis,MAD", storage)
    assert job is None and "via hub: LIS, MAD" in out
    assert storage.list_routes()[0].hubs == ["LIS", "MAD"]


def test_criar_with_auto_hubs_queues_discovery(storage):
    out, job = dispatch_message("/criar GRU ATH 2027-04-01..2027-04-30 10-15 3500 --hubs auto", storage)
    assert "criada" in out and "procurando hubs" in out
    assert job == Job(kind="discover_hubs", payload={"route_id": 1})
    assert storage.list_routes()[0].hubs == []  # só grava depois da descoberta


def test_criar_rejects_bad_hub_code(storage):
    assert "aeroporto" in handle_message("/criar GRU ATH 2027-04-01..2027-04-30 10-15 3500 --hubs LISBOA", storage)


def test_editar_hubs_set_and_clear(storage):
    seed_route(storage)
    out = handle_message("/editar 1 hubs LIS,MAD", storage)
    assert storage.get_route(1).hubs == ["LIS", "MAD"] and "via hub" in out
    handle_message("/editar 1 hubs -", storage)
    assert storage.get_route(1).hubs == []


def test_editar_hubs_auto_returns_job(storage):
    seed_route(storage)
    _out, job = dispatch_message("/editar 1 hubs auto", storage)
    assert job.kind == "discover_hubs" and job.payload == {"route_id": 1}


def test_hubs_command_returns_report_job(storage):
    out, job = dispatch_message("/hubs SAO ATH 2027-04-01..2027-06-30 10-15 LIS,MAD", storage)
    assert "Comparando" in out
    assert job.kind == "hubs_report"
    assert job.payload["hubs"] == ["LIS", "MAD"] and job.payload["return_min"] == 10


def test_hubs_command_usage(storage):
    assert "uso: /hubs" in handle_message("/hubs SAO ATH", storage)


def test_list_table_shows_hub_when_cheaper(storage):
    from dataclasses import replace

    from conftest import make_offer

    r = storage.get_route(seed_route(storage, dest="ATH", target_price=3500.0, hubs="LIS"))
    storage.record(make_offer(r, 3800.0))
    storage.record(replace(make_offer(r, 13100.0), route_key=f"{r.key}@LIS"))
    assert " 3800 -" in handle_message("/monitorias", storage)
    storage.record(replace(make_offer(r, 3100.0), route_key=f"{r.key}@LIS"))
    out = handle_message("/monitorias", storage)
    assert "Via" in out and " 3100 LIS" in out
    pre_body = out.split("<pre>")[1].split("</pre>")[0]
    assert max(len(line) for line in pre_body.splitlines()) <= 32


def test_run_job_discover_saves_chosen_hubs(storage, monkeypatch, fake_telegram):
    from monitor import bot as bot_mod
    from monitor.hubs import Discovery

    seed_route(storage, dest="ATH")
    monkeypatch.setattr("monitor.hubs.discover", lambda source, route: Discovery(direct=None, chosen=["MAD"]))
    monkeypatch.setattr(bot_mod, "TelegramClient", lambda: fake_telegram)
    bot_mod.run_job(Job(kind="discover_hubs", payload={"route_id": 1}), storage)
    assert storage.get_route(1).hubs == ["MAD"]
    assert "Monitorando direto + MAD" in fake_telegram.sent[0][1]
