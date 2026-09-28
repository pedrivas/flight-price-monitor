from __future__ import annotations

import argparse
import os
import sys
import traceback
from dataclasses import dataclass, field
from datetime import date

from .airports import city_country
from .config import has_no_alert_criteria
from .models import RouteQuery
from .notifier import esc
from .storage import Storage
from .telegram import TelegramClient

HELP = (
    "<b>Comandos</b>\n"
    "/monitorias — lista as monitorias ativas\n"
    "/criar ORIG DEST IDA_DE..IDA_ATE NOITES ALVO [DROP%] [--nonstop] [--pax N]\n"
    "    ex: <code>/criar GRU BEL 2026-09-04..2026-09-11 7-21 1700 15</code>\n"
    "    só-ida: use <code>-</code> em NOITES\n"
    "/editar ID CAMPO VALOR — campos: nome alvo drop pax nonstop ida_de ida_ate noites\n"
    "    só ID (sem campo/valor) mostra o detalhe daquela rota\n"
    "    ex: <code>/editar 3 alvo 1600</code>\n"
    "/excluir ID — remove (confirme com <code>/excluir ID sim</code>)\n"
    "/pausar ID   /ativar ID\n"
    "/explorar ORIG IDA_DE..IDA_ATE VOLTA_DE..VOLTA_ATE TETO [DEST1,DEST2,...]\n"
    "    ex: <code>/explorar GRU 2026-10-01..2026-10-08 2026-10-15..2026-10-22 1800</code>\n"
    "    demora alguns minutos; o resultado chega em mensagem separada\n"
    "/varrer — força a varredura de preços agora, fora do gate de 6h"
)


@dataclass
class Job:
    """Trabalho demorado que um comando pode gerar. `dispatch_message` só
    monta o Job — quem executa é `run_job`, chamado pelo worker "lento" do
    server.py (ou direto, de forma síncrona, no modo polling local)."""

    kind: str  # "sweep" | "explore"
    payload: dict = field(default_factory=dict)


class CommandError(Exception):
    """Erro de uso — a mensagem vai direto pro usuário."""


# --- parsing helpers -------------------------------------------------------
def _date(s: str) -> str:
    try:
        return date.fromisoformat(s).isoformat()
    except ValueError:
        raise CommandError(f"data inválida: '{s}' (use AAAA-MM-DD)")


def _date_range(s: str) -> tuple[str, str]:
    if ".." not in s:
        raise CommandError(f"janela de ida inválida: '{s}' (use AAAA-MM-DD..AAAA-MM-DD)")
    a, b = s.split("..", 1)
    lo, hi = _date(a), _date(b)
    if lo > hi:
        raise CommandError("IDA_DE não pode ser depois de IDA_ATE")
    return lo, hi


def _nights(s: str) -> tuple[int | None, int | None]:
    if s == "-":
        return None, None
    try:
        if "-" in s:
            lo, hi = (int(x) for x in s.split("-", 1))
        else:
            lo = hi = int(s)
    except ValueError:
        raise CommandError(f"NOITES inválido: '{s}' (use '7-21', '10' ou '-')")
    if lo > hi or lo < 0:
        raise CommandError("NOITES: mínimo maior que máximo")
    return lo, hi


def _price(s: str) -> float | None:
    if s == "-":
        return None
    try:
        v = float(s.replace(",", "."))
    except ValueError:
        raise CommandError(f"valor numérico inválido: '{s}'")
    if v <= 0:
        raise CommandError("o valor precisa ser positivo")
    return v


def _airport(s: str) -> str:
    s = s.upper()
    if len(s) != 3 or not s.isalpha():
        raise CommandError(f"código de aeroporto inválido: '{s}' (3 letras, ex GRU)")
    return s


def _route_line(r: RouteQuery, storage: Storage) -> str:
    if r.return_after_days:
        lo, hi = r.return_after_days
        nights = f"{lo} noites" if lo == hi else f"{lo}–{hi} noites"
    else:
        nights = "só ida"
    crit = []
    if r.target_price is not None:
        crit.append(f"alvo {r.currency} {r.target_price:.0f}")
    if r.drop_pct is not None:
        crit.append(f"queda {r.drop_pct:.0f}%")
    last = storage.last_price(r.key)
    last_txt = f" · último: {r.currency} {last:.0f}" if last is not None else ""
    city, country = city_country(r.dest)
    return (
        f"<b>#{r.id}</b> · {esc(r.name)} ({esc(city)}, {esc(country)})\n"
        f"   {r.origin}→{r.dest} · {r.depart_range[0]}→{r.depart_range[1]} · {nights} · {r.adults} pax\n"
        f"   {esc(' · '.join(crit) or 'sem critério de alerta')}{last_txt}"
    )


def _routes_table(routes: list[RouteQuery], storage: Storage) -> str:
    """Tabela alinhada em fonte monoespaçada — Telegram não tem <table> no
    HTML dele, então um bloco <pre> com colunas de largura fixa é o que
    renderiza como tabela de verdade no app.

    Largura importa mais do que parece: no desktop um <pre> largo rola de
    lado, no app ele QUEBRA LINHA — o que destrói qualquer alinhamento por
    coluna. Por isso o código IATA (3 letras) no lugar do nome da cidade e
    separador de 1 espaço só: mantém a tabela em ~29 colunas, cabe sem
    quebrar até em tela de celular pequena.
    """
    headers = ("#", "Dest", "País", "Alvo", "Último")
    right_aligned = {0, 3, 4}  # #, Alvo, Último — colunas numéricas

    rows = []
    for r in routes:
        _city, country = city_country(r.dest)
        alvo = f"{r.target_price:.0f}" if r.target_price is not None else "-"
        last = storage.last_price(r.key)
        ultimo = f"{last:.0f}" if last is not None else "-"
        rows.append((str(r.id), r.dest, country, alvo, ultimo))

    widths = [max(len(headers[i]), *(len(row[i]) for row in rows)) for i in range(len(headers))]

    def fmt(cells: tuple[str, ...]) -> str:
        return " ".join(
            c.rjust(w) if i in right_aligned else c.ljust(w) for i, (c, w) in enumerate(zip(cells, widths))
        )

    lines = [fmt(headers), fmt(tuple("-" * w for w in widths)), *(fmt(r) for r in rows)]
    return "<pre>" + esc("\n".join(lines)) + "</pre>"


# --- comandos -------------------------------------------------------------
def cmd_help(args, storage) -> str:
    return HELP


def cmd_list(args, storage) -> str:
    routes = storage.list_routes(active_only=True)
    if not routes:
        return "Nenhuma monitoria ativa. Crie uma com /criar."
    return (
        f"📋 <b>Monitorias ativas</b>\n\n{_routes_table(routes, storage)}\n"
        f"<i>valores em R$ · detalhe de uma rota: /editar ID</i>"
    )


def cmd_create(args, storage) -> str:
    if len(args) < 5:
        raise CommandError("faltam argumentos.\n\n" + HELP)
    origin = _airport(args[0])
    dest = _airport(args[1])
    depart_from, depart_to = _date_range(args[2])
    return_min, return_max = _nights(args[3])
    target = _price(args[4])

    drop = None
    nonstop = 0
    adults = 1
    rest = list(args[5:])
    while rest:
        tok = rest.pop(0)
        if tok == "--nonstop":
            nonstop = 1
        elif tok == "--pax":
            if not rest:
                raise CommandError("--pax precisa de um número")
            adults = int(rest.pop(0))
        elif drop is None:
            drop = _price(tok)
            if drop > 100:
                raise CommandError("DROP% deve estar entre 1 e 100")
        else:
            raise CommandError(f"argumento não reconhecido: '{tok}'")

    fields = dict(
        name=f"{origin}→{dest}", origin=origin, dest=dest,
        depart_from=depart_from, depart_to=depart_to,
        return_min=return_min, return_max=return_max,
        adults=adults, target_price=target, drop_pct=drop,
        nonstop=nonstop, currency="BRL", active=1,
    )
    probe = RouteQuery(
        name="", origin=origin, dest=dest,
        depart_range=(date.fromisoformat(depart_from), date.fromisoformat(depart_to)),
        target_price=target, drop_pct=drop,
    )
    if has_no_alert_criteria(probe):
        raise CommandError("defina ao menos ALVO ou DROP% — senão nunca alerta")

    new_id = storage.add_route(**fields)
    warn = "" if depart_from > date.today().isoformat() else "\n⚠️ janela de ida no passado"
    return f"✅ Monitoria <b>#{new_id}</b> criada: {origin}→{dest}{warn}"


_EDIT_FIELDS = {
    "nome": "name", "alvo": "target_price", "drop": "drop_pct", "pax": "adults",
    "nonstop": "nonstop", "ida_de": "depart_from", "ida_ate": "depart_to",
}


def cmd_edit(args, storage) -> str:
    if not args:
        raise CommandError("uso: /editar ID [CAMPO VALOR]  (só ID mostra o detalhe da rota)")
    if len(args) == 1:
        route_id = _int_id(args[0])
        route = storage.get_route(route_id)
        if route is None:
            raise CommandError(f"monitoria #{route_id} não existe")
        return _route_line(route, storage)
    if len(args) < 3:
        raise CommandError("uso: /editar ID CAMPO VALOR")
    route_id = _int_id(args[0])
    field = args[1].lower()
    value_raw = " ".join(args[2:])
    if storage.get_route(route_id) is None:
        raise CommandError(f"monitoria #{route_id} não existe")

    if field == "noites":
        lo, hi = _nights(value_raw)
        storage.update_route(route_id, return_min=lo, return_max=hi)
    elif field == "nonstop":
        storage.update_route(route_id, nonstop=1 if _flag(value_raw) else 0)
    elif field in ("alvo", "drop"):
        v = _price(value_raw)
        if field == "drop" and v is not None and v > 100:
            raise CommandError("DROP% deve estar entre 1 e 100")
        storage.update_route(route_id, **{_EDIT_FIELDS[field]: v})
    elif field == "pax":
        storage.update_route(route_id, adults=int(value_raw))
    elif field in ("ida_de", "ida_ate"):
        storage.update_route(route_id, **{_EDIT_FIELDS[field]: _date(value_raw)})
    elif field == "nome":
        storage.update_route(route_id, name=value_raw)
    else:
        raise CommandError(f"campo desconhecido: '{field}'\ncampos: {', '.join(_EDIT_FIELDS)}, noites")

    return f"✏️ #{route_id} atualizada.\n\n{_route_line(storage.get_route(route_id), storage)}"


def cmd_delete(args, storage) -> str:
    if not args:
        raise CommandError("uso: /excluir ID")
    route_id = _int_id(args[0])
    route = storage.get_route(route_id)
    if route is None or not route.active:
        raise CommandError(f"monitoria #{route_id} não existe ou já foi removida")
    if len(args) < 2 or args[1].lower() != "sim":
        return f"Remover <b>#{route_id}</b> ({esc(route.name)})? Confirme: <code>/excluir {route_id} sim</code>"
    storage.set_route_active(route_id, False)
    return f"🗑️ Monitoria #{route_id} removida."


def cmd_pause(args, storage) -> str:
    return _toggle(args, storage, active=False, verb="pausada")


def cmd_activate(args, storage) -> str:
    return _toggle(args, storage, active=True, verb="reativada")


def cmd_explore(args, storage) -> tuple[str, Job]:
    if len(args) < 4:
        raise CommandError(
            "uso: /explorar ORIG IDA_DE..IDA_ATE VOLTA_DE..VOLTA_ATE TETO [DEST1,DEST2,...]"
        )
    from . import explore as explore_module  # import tardio: evita ciclo no carregamento do módulo

    origin = _airport(args[0])
    try:
        depart_range = explore_module._parse_range(args[1])
        return_range = explore_module._parse_range(args[2])
    except argparse.ArgumentTypeError as exc:
        raise CommandError(str(exc))
    max_price = _price(args[3])
    if max_price is None:
        raise CommandError("TETO precisa ser um valor positivo")
    payload = dict(
        origin=origin, depart_range=depart_range, return_range=return_range,
        max_price=max_price, destinations=args[4] if len(args) > 4 else "",
    )
    return "🔎 Rodando a busca (alguns minutos)… mando o resultado aqui.", Job(kind="explore", payload=payload)


def cmd_sweep_now(args, storage) -> tuple[str, Job]:
    return "🔄 Varredura forçada, iniciando agora…", Job(kind="sweep")


def run_job(job: Job, storage: Storage) -> None:
    """Executa um Job de verdade. Chamado pelo worker lento do server.py, ou
    de forma síncrona no modo polling local (sem fila pra enfileirar nele)."""
    if job.kind == "sweep":
        from . import main as main_mod  # import tardio: main.py importa bot.py no nível do módulo

        main_mod.run_sweep(storage, dry_run=False, source_name=os.environ.get("PRICE_SOURCE", "fastflights"))
        storage.mark_sweep_done()
    elif job.kind == "explore":
        from . import explore as explore_module

        p = job.payload
        dests = None
        if p.get("destinations"):
            codes = [c.strip().upper() for c in p["destinations"].replace(";", ",").split(",") if c.strip()]
            dests = {c: explore_module.DEFAULT_DESTS.get(c, c) for c in codes}
        under, near = explore_module.run_explore(
            p["origin"], p["depart_range"], p["return_range"], p["max_price"], dests=dests,
        )
        text = explore_module.format_results(under, near, p["origin"], p["max_price"], "BRL")
        TelegramClient().send_message(text)
    else:
        print(f"[erro] job desconhecido: {job.kind}", file=sys.stderr)


def _toggle(args, storage, active: bool, verb: str) -> str:
    if not args:
        raise CommandError("informe o ID")
    route_id = _int_id(args[0])
    if not storage.set_route_active(route_id, active):
        raise CommandError(f"monitoria #{route_id} não existe")
    return f"#{route_id} {verb}."


def _int_id(s: str) -> int:
    try:
        return int(s.lstrip("#"))
    except ValueError:
        raise CommandError(f"ID inválido: '{s}'")


def _flag(s: str) -> bool:
    return s.strip().lower() in ("sim", "true", "1", "yes", "on")


COMMANDS = {
    "start": cmd_help, "help": cmd_help, "ajuda": cmd_help,
    "monitorias": cmd_list, "listar": cmd_list, "list": cmd_list,
    "criar": cmd_create, "novo": cmd_create,
    "editar": cmd_edit,
    "excluir": cmd_delete, "remover": cmd_delete,
    "pausar": cmd_pause, "ativar": cmd_activate,
}

# Comandos que disparam trabalho demorado — devolvem (resposta imediata, Job).
JOB_COMMANDS = {
    "explorar": cmd_explore,
    "varrer": cmd_sweep_now,
}


def dispatch_message(text: str, storage: Storage) -> tuple[str, Job | None]:
    """Como handle_message, mas também devolve o Job (se houver) pro chamador
    executar. `handle_message` é um wrapper fino em cima desta função."""
    parts = text.strip().split()
    if not parts or not parts[0].startswith("/"):
        return "", None
    cmd = parts[0].split("@", 1)[0].lstrip("/").lower()
    args = parts[1:]
    try:
        if cmd in JOB_COMMANDS:
            return JOB_COMMANDS[cmd](args, storage)
        handler = COMMANDS.get(cmd)
        if handler is None:
            return f"Comando desconhecido: /{esc(cmd)}\n\n{HELP}", None
        return handler(args, storage), None
    except CommandError as exc:
        return f"⚠️ {exc}", None


def handle_message(text: str, storage: Storage) -> str:
    reply, _job = dispatch_message(text, storage)
    return reply


def _allowed_chat_ids() -> set[int]:
    raw = os.environ.get("TELEGRAM_ALLOWED_CHAT_IDS") or os.environ.get("TELEGRAM_CHAT_ID", "")
    ids = {int(x) for x in raw.replace(";", ",").split(",") if x.strip().lstrip("-").isdigit()}
    if not ids:
        print("[aviso] nenhum chat permitido configurado — bot aceita qualquer chat", file=sys.stderr)
    return ids


def handle_update(
    update: dict,
    storage: Storage,
    telegram: TelegramClient,
    allowed: set[int],
    on_job=None,
) -> bool:
    """Processa um único update: filtra chat, despacha, responde, encaminha o
    Job (se houver). Devolve True se respondeu. Usado pelo polling e pelo
    webhook (server.py passa `on_job=slow_queue.put` pra não bloquear o worker
    rápido com uma varredura/explore; sem isso, roda na hora)."""
    msg = update.get("message") or update.get("edited_message")
    if not msg or "text" not in msg:
        return False
    chat_id = msg["chat"]["id"]
    if allowed and chat_id not in allowed:
        return False
    try:
        reply, job = dispatch_message(msg["text"], storage)
    except Exception:
        traceback.print_exc()
        reply, job = "⚠️ erro interno ao processar o comando", None
    if reply:
        telegram.send_message(reply, chat_id=chat_id)
    if job is not None:
        (on_job or (lambda j: run_job(j, storage)))(job)
    return bool(reply)


def poll_and_handle(storage: Storage, telegram: TelegramClient | None = None) -> int:
    """Lê comandos novos do Telegram, executa e responde. Devolve quantos tratou."""
    telegram = telegram or TelegramClient()
    allowed = _allowed_chat_ids()
    last = storage.kv_get("telegram_offset")
    offset = int(last) + 1 if last else None

    handled = 0
    max_id: int | None = None
    for update in telegram.get_updates(offset=offset):
        max_id = update["update_id"]
        if handle_update(update, storage, telegram, allowed):
            handled += 1

    if max_id is not None:
        storage.kv_set("telegram_offset", str(max_id))
    return handled
