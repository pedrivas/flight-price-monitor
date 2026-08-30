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
    notifier = None if dry_run else TelegramNotifier()

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
        storage.record(cheapest)
        decision = evaluate(route, cheapest, storage)
        base = f"{decision.baseline:.0f}" if decision.baseline else "s/ histórico"
        print(f"[info] {route.name}: menor {cheapest.currency} {cheapest.price:.0f} (mediana 30d: {base})")

        if decision.should_alert:
            msg = format_alert(route, cheapest, decision)
            if dry_run:
                print("---- ALERTA (dry-run) ----\n" + msg + "\n--------------------------")
            else:
                notifier.send(msg)
                storage.mark_alerted(cheapest.route_key, cheapest.price)
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
