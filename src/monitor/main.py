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

from .config import load_routes
from .notifier import TelegramNotifier, format_alert
from .rules import evaluate
from .sources import get_source
from .storage import Storage


def run(dry_run: bool = False, source_name: str = "fastflights") -> int:
    load_dotenv()
    routes = load_routes()
    source = get_source(source_name)
    storage = Storage()
    notifier = None  # criado sob demanda, só quando há alerta a enviar
    delivery_broken = False  # 1ª falha de envio rebaixa o resto para só-impressão

    alerts = 0
    for route in routes:
        try:
            offers = source.search(route)
        except Exception:
            print(f"[erro] falha ao buscar {route.name}:\n{traceback.format_exc()}", file=sys.stderr)
            continue

        if not offers:
            print(f"[info] {route.name}: nenhuma oferta")
            continue

        cheapest = min(offers, key=lambda o: o.price)
        decision = evaluate(route, cheapest, storage)  # antes de gravar: baseline sem a obs. atual
        storage.record(cheapest)
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


def main() -> None:
    p = argparse.ArgumentParser(description="Monitor de passagens em promoção")
    p.add_argument("--dry-run", action="store_true", help="não envia no Telegram, só imprime")
    p.add_argument("--source", default=os.environ.get("PRICE_SOURCE", "fastflights"))
    args = p.parse_args()
    run(dry_run=args.dry_run, source_name=args.source)


if __name__ == "__main__":
    main()
