from __future__ import annotations

import argparse
import os
import sys
import traceback

from dotenv import load_dotenv

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")  # console Windows usa cp1252 por padrão
    except (AttributeError, ValueError):
        pass

from .bot import handle_message, poll_and_handle
from .config import CONFIG_PATH, load_routes_from_yaml
from .notifier import TelegramNotifier, esc, format_alert
from .rules import evaluate
from .sources import get_source
from .storage import Storage
from .telegram import TelegramClient

SWEEP_INTERVAL_H = 6


def run_sweep(storage: Storage, dry_run: bool = False, source_name: str = "fastflights") -> int:
    source = get_source(source_name)
    notifier = None  # criado sob demanda, só quando há alerta a enviar
    delivery_broken = False  # 1ª falha de envio rebaixa o resto para só-impressão

    routes = storage.list_routes(active_only=True)
    alerts = 0
    for route in routes:
        # busca + leitura/gravação no banco: uma falha aqui não derruba as outras rotas
        try:
            offers = source.search(route)
            if not offers:
                print(f"[info] {route.name}: nenhuma oferta")
                continue
            cheapest = min(offers, key=lambda o: o.price)
            decision = evaluate(route, cheapest, storage)  # antes de gravar: baseline sem a obs. atual
            storage.record(cheapest)
        except Exception:
            print(f"[erro] {route.name}:\n{traceback.format_exc()}", file=sys.stderr)
            continue

        base = f"{decision.baseline:.0f}" if decision.baseline is not None else "s/ histórico"
        print(f"[info] {route.name}: menor {cheapest.currency} {cheapest.price:.0f} (mediana 30d: {base})")

        if decision.should_alert:
            msg = format_alert(route, cheapest, decision)
            if dry_run or delivery_broken:
                print("---- ALERTA (não enviado) ----\n" + msg + "\n------------------------------")
            else:
                try:
                    notifier = notifier or TelegramNotifier()
                    notifier.send(msg)
                    storage.mark_alerted(cheapest.route_key, cheapest.price)
                except Exception as exc:
                    delivery_broken = True
                    print(f"[aviso] alerta não enviado ({exc}):\n{msg}", file=sys.stderr)
            alerts += 1

    print(f"[done] {len(routes)} rotas, {alerts} alerta(s)")
    return alerts


def run_command(storage: Storage, command: str, dry_run: bool = False) -> str:
    """Executa um comando do bot direto (via --command / workflow_dispatch),
    sem passar pelo Telegram. Ecoa a resposta no grupo se der."""
    command = command.strip()
    if command and not command.startswith("/"):
        command = "/" + command  # tolera 'excluir 3' no formulário do dispatch
    reply = handle_message(command, storage) or "(sem resposta)"
    print(reply)
    if not dry_run:
        try:
            TelegramClient().send_message(f"↩️ <code>{esc(command)}</code>\n{reply}")
        except Exception as exc:
            print(f"[aviso] não ecoei no Telegram ({exc})", file=sys.stderr)
    return reply


def tick(
    dry_run: bool = False,
    source_name: str = "fastflights",
    force_sweep: bool = False,
    skip_bot: bool = False,
    skip_sweep: bool = False,
    command: str | None = None,
) -> None:
    load_dotenv()
    storage = Storage()
    storage.seed_routes(load_routes_from_yaml(CONFIG_PATH))

    if command:
        run_command(storage, command, dry_run=dry_run)
        return

    if not skip_bot:
        try:
            n = poll_and_handle(storage)
            if n:
                print(f"[bot] {n} comando(s) tratado(s)")
        except Exception:
            print(f"[erro] bot:\n{traceback.format_exc()}", file=sys.stderr)  # nunca bloqueia a varredura

    if skip_sweep:
        return
    due = force_sweep or storage.hours_since_last_sweep() >= SWEEP_INTERVAL_H
    if not due:
        print(f"[info] varredura pulada ({storage.hours_since_last_sweep():.1f}h desde a última)")
        return
    run_sweep(storage, dry_run=dry_run, source_name=source_name)
    storage.mark_sweep_done()


def main() -> None:
    p = argparse.ArgumentParser(description="Monitor de passagens em promoção")
    p.add_argument("--dry-run", action="store_true", help="não envia alertas no Telegram")
    p.add_argument("--source", default=os.environ.get("PRICE_SOURCE", "fastflights"))
    p.add_argument("--sweep-now", action="store_true", help="força a varredura de preços agora")
    p.add_argument("--no-bot", action="store_true", help="não processa comandos do Telegram")
    p.add_argument("--bot-only", action="store_true", help="só processa comandos, sem varredura")
    p.add_argument("--command", help="executa um comando do bot agora (ex: '/excluir 3') e sai")
    args = p.parse_args()
    tick(
        dry_run=args.dry_run,
        source_name=args.source,
        force_sweep=args.sweep_now,
        skip_bot=args.no_bot,
        skip_sweep=args.bot_only,
        command=args.command,
    )


if __name__ == "__main__":
    main()
