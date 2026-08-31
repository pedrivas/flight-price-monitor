from __future__ import annotations

from conftest import seed_route

from monitor.bot import handle_message, poll_and_handle


# --- handle_message: comandos individuais ---------------------------------
def test_help(storage):
    assert "Comandos" in handle_message("/help", storage)
    assert "Comandos" in handle_message("/start@meu_bot", storage)


def test_list_empty(storage):
    assert "Nenhuma monitoria" in handle_message("/monitorias", storage)


def test_list_shows_routes(storage):
    seed_route(storage, name="GRU→BEL", dest="BEL", target_price=1700.0)
    out = handle_message("/monitorias", storage)
    assert "GRU→BEL" in out and "#1" in out and "1700" in out


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
