"""Busca exploratória: varre vários destinos a partir de uma origem, ida-e-volta
dentro de uma janela de datas, e lista os que ficam abaixo de um teto.

Operação cara (~25 destinos × ~4 datas). Roda sob demanda — CLI ou o workflow
`explorar` — nunca dentro do tick do monitor. Ver ADR-007.

    python -m monitor.explore --depart 2026-10-01..2026-10-08 \\
        --return 2026-10-15..2026-10-22 --max 1800 [--destinations REC,SSA]
"""
from __future__ import annotations

import argparse
import sys
import traceback
from dataclasses import dataclass
from datetime import date

from dotenv import load_dotenv

from .models import Offer, RouteQuery
from .notifier import esc
from .sources import get_source
from .sources.base import PriceSource
from .telegram import TelegramClient

DEFAULT_DESTS: dict[str, str] = {
    # Brasil
    "REC": "Recife", "SSA": "Salvador", "FOR": "Fortaleza", "NAT": "Natal",
    "MCZ": "Maceió", "JPA": "João Pessoa", "SLZ": "São Luís", "BEL": "Belém",
    "POA": "Porto Alegre", "CWB": "Curitiba", "FLN": "Florianópolis",
    "IGU": "Foz do Iguaçu", "BSB": "Brasília", "CNF": "Belo Horizonte",
    "GIG": "Rio de Janeiro", "VIX": "Vitória", "CGB": "Cuiabá", "GYN": "Goiânia",
    "BPS": "Porto Seguro", "IOS": "Ilhéus",
    # América do Sul
    "EZE": "Buenos Aires", "SCL": "Santiago", "MVD": "Montevidéu",
    "ASU": "Assunção", "LIM": "Lima", "BOG": "Bogotá", "MDE": "Medellín",
}

NEAR_MISS_FACTOR = 1.2  # "quase-lá": até 20% acima do teto


@dataclass
class ExploreHit:
    code: str
    name: str
    offer: Offer

    @property
    def price(self) -> float:
        return self.offer.price


def _parse_range(s: str) -> tuple[date, date]:
    if ".." not in s:
        raise argparse.ArgumentTypeError(f"'{s}': use AAAA-MM-DD..AAAA-MM-DD")
    a, b = s.split("..", 1)
    try:
        lo, hi = date.fromisoformat(a.strip()), date.fromisoformat(b.strip())
    except ValueError:
        raise argparse.ArgumentTypeError(f"'{s}': data inválida (use AAAA-MM-DD..AAAA-MM-DD)")
    if lo > hi:
        raise argparse.ArgumentTypeError(f"'{s}': início depois do fim")
    return lo, hi


def _mid(rng: tuple[date, date]) -> date:
    return rng[0] + (rng[1] - rng[0]) / 2


def _window_to_nights(depart_range: tuple[date, date], return_range: tuple[date, date]) -> int:
    """Janela de volta -> nº de noites, medido entre os pontos médios das janelas."""
    return max((_mid(return_range) - _mid(depart_range)).days, 1)


def run_explore(
    origin: str,
    depart_range: tuple[date, date],
    return_range: tuple[date, date],
    max_price: float,
    *,
    adults: int = 1,
    currency: str = "BRL",
    dests: dict[str, str] | None = None,
    source: PriceSource | None = None,
) -> tuple[list[ExploreHit], list[ExploreHit]]:
    """Devolve (dentro_do_teto, quase_lá), ambos ordenados por preço."""
    source = source or get_source("fastflights")
    dests = dests or DEFAULT_DESTS
    nights = _window_to_nights(depart_range, return_range)

    hits: list[ExploreHit] = []
    for code, name in dests.items():
        route = RouteQuery(
            name=name, origin=origin.upper(), dest=code.upper(),
            depart_range=depart_range, return_after_days=(nights, nights),
            adults=adults, currency=currency,
        )
        try:
            offers = source.search(route)
        except Exception:
            print(f"[erro] {code} {name}:\n{traceback.format_exc()}", file=sys.stderr)
            continue
        if not offers:
            print(f"[info] {code} {name}: sem resultado")
            continue
        cheapest = min(offers, key=lambda o: o.price)
        hits.append(ExploreHit(code, name, cheapest))
        mark = "OK " if cheapest.price <= max_price else "   "
        print(f"{mark}{code} {name}: {currency} {cheapest.price:.0f}")

    under = sorted((h for h in hits if h.price <= max_price), key=lambda h: h.price)
    near = sorted(
        (h for h in hits if max_price < h.price <= max_price * NEAR_MISS_FACTOR),
        key=lambda h: h.price,
    )[:4]
    return under, near


def _hit_line(h: ExploreHit, currency: str) -> str:
    o = h.offer
    stops = "direto" if o.stops == 0 else f"{o.stops} esc"
    volta = f" · volta {o.return_date}" if o.return_date else ""
    return (
        f"<b>{currency} {o.price:,.0f}</b> — {esc(h.name)} ({h.code})\n"
        f"   ida {o.depart_date}{volta} · {esc(o.carrier)} · {stops}"
    )


def format_results(
    under: list[ExploreHit],
    near: list[ExploreHit],
    origin: str,
    max_price: float,
    currency: str,
) -> str:
    if not under and not near:
        return f"🔎 <b>Explore {origin}</b>\n\nNada encontrado nas datas/destinos testados."

    parts = [f"🔎 <b>Explore {origin} · até {currency} {max_price:,.0f}</b>"]
    if under:
        parts.append("\n".join(_hit_line(h, currency) for h in under))
    else:
        parts.append("Nada abaixo do teto.")
    if near:
        parts.append(
            "<i>quase lá:</i>\n" + "\n".join(_hit_line(h, currency) for h in near)
        )
    return "\n\n".join(parts)


def main(argv: list[str] | None = None) -> None:
    load_dotenv()
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass

    p = argparse.ArgumentParser(description="Busca exploratória de passagens ida-e-volta")
    p.add_argument("--origin", default="GRU")
    p.add_argument("--depart", required=True, type=_parse_range, help="AAAA-MM-DD..AAAA-MM-DD")
    p.add_argument("--return", dest="return_", required=True, type=_parse_range, help="AAAA-MM-DD..AAAA-MM-DD")
    p.add_argument("--max", dest="max_price", type=float, default=1800.0)
    p.add_argument("--adults", type=int, default=1)
    p.add_argument("--currency", default="BRL")
    p.add_argument("--destinations", default="", help="códigos IATA separados por vírgula (vazio = lista padrão)")
    p.add_argument("--source", default="fastflights")
    p.add_argument("--dry-run", action="store_true", help="não envia no Telegram")
    args = p.parse_args(argv)

    dests = None
    if args.destinations.strip():
        codes = [c.strip().upper() for c in args.destinations.replace(";", ",").split(",") if c.strip()]
        dests = {c: DEFAULT_DESTS.get(c, c) for c in codes}

    under, near = run_explore(
        args.origin, args.depart, args.return_, args.max_price,
        adults=args.adults, currency=args.currency, dests=dests,
        source=get_source(args.source),
    )
    text = format_results(under, near, args.origin.upper(), args.max_price, args.currency)
    print("\n" + text)
    if not args.dry_run:
        TelegramClient().send_message(text)


if __name__ == "__main__":
    main()
