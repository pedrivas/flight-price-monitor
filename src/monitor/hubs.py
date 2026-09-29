"""Estratégia de hub: duas passagens separadas em vez de uma direta. Ver ADR-009.

Ida e volta vira dois bilhetes ida-e-volta, o de dentro contido no de fora:

    externo  origem ⇄ hub     ida d       volta d+N
    interno  hub ⇄ destino    ida d+2     volta d+N-2

Os 2 dias de folga no hub existem porque o voo Brasil→Europa sai à noite e
chega no dia seguinte, e porque com bilhetes separados ninguém te realoca se
o primeiro atrasar. Só ida: origem→hub em d, hub→destino em d+2.

Uso avulso (mesmo relatório do comando /hubs):
    python -m monitor.hubs SAO ATH 2027-04-01..2027-06-30 10-15 [--hubs LIS,MAD] [--dry-run]
"""
from __future__ import annotations

import argparse
import os
import sys
from collections import defaultdict
from dataclasses import dataclass, field, replace
from datetime import date, timedelta

from dotenv import load_dotenv

from .airports import city_country, region
from .dates import sample_dates
from .models import Offer, RouteQuery
from .notifier import esc
from .sources.base import PriceSource

LAYOVER_DAYS = 2
MIN_NIGHTS = 2 * LAYOVER_DAYS + 1  # o bilhete de dentro precisa de pelo menos 1 noite

# Candidatos pensados pra quem sai do Brasil, por região do destino. A
# descoberta (discover) testa todos e só fica com os que batem o direto.
HUB_CANDIDATES: dict[str, list[str]] = {
    "eu": ["LIS", "MAD", "LHR", "FCO", "CDG", "FRA", "AMS", "IST"],
    "me": ["IST", "DOH", "DXB", "LIS", "MAD"],
    "asia": ["IST", "DOH", "DXB", "LIS", "MAD"],
    "oc": ["DOH", "DXB", "SCL", "JNB"],
    "af": ["LIS", "MAD", "CMN", "ADD", "JNB"],
    "na": ["MIA", "FLL", "MCO", "PTY"],
    "sa": ["PTY", "BOG", "LIM", "SCL"],
}
GLOBAL_CANDIDATES = ["LIS", "MAD", "MIA", "PTY", "IST", "DOH"]


def candidate_hubs(origin: str, dest: str) -> list[str]:
    cands = HUB_CANDIDATES.get(region(dest), GLOBAL_CANDIDATES)
    return [h for h in cands if h not in (origin.upper(), dest.upper())]


def _nights(route: RouteQuery) -> int | None:
    if not route.return_after_days:
        return None
    lo, hi = route.return_after_days
    return (lo + hi) // 2  # mesmo ponto médio que a busca direta usa


def _quote_best(source: PriceSource, cache: dict | None, route: RouteQuery,
                o: str, d: str, dep: date, ret: date | None) -> Offer | None:
    k = (o, d, dep, ret, route.adults, route.nonstop)
    if cache is not None and k in cache:
        return cache[k]
    offers = source.quote(o, d, dep, ret, adults=route.adults,
                          currency=route.currency, nonstop=route.nonstop)
    best = min(offers, key=lambda x: x.price) if offers else None
    if cache is not None:
        cache[k] = best
    return best


def search_via(source: PriceSource, route: RouteQuery, hub: str,
               cache: dict | None = None, dates: list[date] | None = None) -> Offer | None:
    """Melhor combinação de 2 bilhetes via `hub` nas datas da rota, ou None.

    Levanta NotImplementedError se a fonte não tem `quote` — quem chama decide
    se pula o hub ou avisa."""
    nights = _nights(route)
    if nights is not None and nights < MIN_NIGHTS:
        print(f"[hub] {route.name}: {nights} noites < {MIN_NIGHTS}, sem espaço pra folga no hub — pulando {hub}",
              file=sys.stderr)
        return None

    best: Offer | None = None
    for dep in dates if dates is not None else sample_dates(*route.depart_range):
        if nights is None:
            ret = None
            outer = _quote_best(source, cache, route, route.origin, hub, dep, None)
            inner = _quote_best(source, cache, route, hub, route.dest, dep + timedelta(days=LAYOVER_DAYS), None)
        else:
            ret = dep + timedelta(days=nights)
            outer = _quote_best(source, cache, route, route.origin, hub, dep, ret)
            inner = _quote_best(source, cache, route, hub, route.dest,
                                dep + timedelta(days=LAYOVER_DAYS), ret - timedelta(days=LAYOVER_DAYS))
        if outer is None or inner is None:
            continue
        total = outer.price + inner.price
        if best is None or total < best.price:
            key = f"{route.key}@{hub}"
            best = Offer(
                route_key=key,
                price=total,
                currency=route.currency,
                depart_date=dep,
                return_date=ret,
                carrier=f"{outer.carrier} + {inner.carrier}",
                stops=outer.stops + 1 + inner.stops,  # a troca no hub conta como parada
                via=hub,
                legs=[replace(outer, route_key=key), replace(inner, route_key=key)],
                origin=route.origin,
                dest=route.dest,
            )
    return best


def _direct_best(source: PriceSource, cache: dict | None, route: RouteQuery, dates: list[date]) -> Offer | None:
    nights = _nights(route)
    best = None
    for dep in dates:
        ret = dep + timedelta(days=nights) if nights is not None else None
        o = _quote_best(source, cache, route, route.origin, route.dest, dep, ret)
        if o and (best is None or o.price < best.price):
            best = o
    return best


# --- descoberta (/criar ... --hubs auto, /editar ID hubs auto) ---------------
@dataclass
class Discovery:
    direct: Offer | None
    ranking: list[tuple[str, Offer | None]] = field(default_factory=list)
    chosen: list[str] = field(default_factory=list)


def discover(source: PriceSource, route: RouteQuery, candidates: list[str] | None = None,
             top: int = 2, max_dates: int = 3, cache: dict | None = None) -> Discovery:
    """Testa cada candidato numa amostra curta de datas e escolhe até `top`
    hubs que batem o direto. Custo: max_dates × (1 + 2 × candidatos) buscas."""
    cache = {} if cache is None else cache
    candidates = candidates if candidates is not None else candidate_hubs(route.origin, route.dest)
    dates = sample_dates(*route.depart_range, max_samples=max_dates)
    direct = _direct_best(source, cache, route, dates)
    ranking = [(h, search_via(source, route, h, cache, dates)) for h in candidates]
    ranking.sort(key=lambda hr: hr[1].price if hr[1] else float("inf"))
    chosen = [h for h, o in ranking if o is not None and (direct is None or o.price < direct.price)][:top]
    return Discovery(direct=direct, ranking=ranking, chosen=chosen)


def _money(v: float) -> str:
    return f"{v:,.0f}".replace(",", ".")


def format_discovery(route: RouteQuery, result: Discovery) -> str:
    city, _ = city_country(route.dest)
    head = f"🧭 <b>Hubs para #{route.id} ({esc(route.origin)}→{esc(city)})</b>\n"
    if result.direct is None:
        head += "direto: sem preço nas datas testadas\n"
    else:
        head += f"direto: R$ {_money(result.direct.price)}\n"
    rows = ["Hub Total  vs dir"]
    for hub, offer in result.ranking:
        if offer is None:
            rows.append(f"{hub:<3} {'—':>6}")
            continue
        diff = f"{offer.price - result.direct.price:+.0f}" if result.direct else ""
        rows.append(f"{hub:<3} {offer.price:>6.0f} {diff:>6}")
    body = "<pre>" + esc("\n".join(rows)) + "</pre>\n"
    if result.chosen:
        names = ", ".join(f"{h} ({city_country(h)[0]})" for h in result.chosen)
        tail = f"✅ Monitorando direto + {esc(names)}"
    else:
        tail = "Nenhum hub bateu o direto — monitorando só o direto."
    return head + body + tail


# --- relatório (/hubs) -------------------------------------------------------
MONTHS = {1: "janeiro", 2: "fevereiro", 3: "março", 4: "abril", 5: "maio", 6: "junho",
          7: "julho", 8: "agosto", 9: "setembro", 10: "outubro", 11: "novembro", 12: "dezembro"}


def report_dates(depart_range: tuple[date, date]) -> list[date]:
    """~1 data por semana: o relatório pode cobrir meses, e cada data custa
    1 + 2×hubs buscas — semanal mantém uma janela de 3 meses em ~200 buscas."""
    days = (depart_range[1] - depart_range[0]).days + 1
    return sample_dates(*depart_range, max_samples=max(4, days // 7))


def hubs_report(source: PriceSource, route: RouteQuery, hubs: list[str] | None = None) -> str:
    hubs = hubs or candidate_hubs(route.origin, route.dest)
    cache: dict = {}
    by_month: dict[int, list[date]] = defaultdict(list)
    for d in report_dates(route.depart_range):
        by_month[(d.year, d.month)].append(d)

    city, _ = city_country(route.dest)
    nights = _nights(route)
    kind = f"ida e volta, {nights} noites" if nights is not None else "só ida"
    parts = [f"🧭 <b>{esc(route.origin)} → {esc(city)} via hub</b> · {kind}"]
    for (_y, m), dates in sorted(by_month.items()):
        direct = _direct_best(source, cache, route, dates)
        options = []
        for h in hubs:
            o = search_via(source, route, h, cache, dates)
            if o is not None:
                options.append((h, o))
        options.sort(key=lambda ho: ho[1].price)
        head = f"<b>{MONTHS[m]}</b> — direto " + (f"R$ {_money(direct.price)}" if direct else "sem preço")
        rows = ["Hub Total  vs dir"]
        for h, o in options:
            diff = f"{o.price - direct.price:+.0f}" if direct else ""
            rows.append(f"{h:<3} {o.price:>6.0f} {diff:>6}")
        section = head + "\n<pre>" + esc("\n".join(rows)) + "</pre>"
        if options and (direct is None or options[0][1].price < direct.price):
            h, o = options[0]
            l1, l2 = o.legs
            arrow = "⇄" if o.return_date else "→"
            section += (f"\nmelhor: {h} — {l1.origin}{arrow}{h} ida {l1.depart_date:%d/%m} + "
                        f"{h}{arrow}{l2.dest} ida {l2.depart_date:%d/%m}")
        parts.append(section)
    parts.append("<i>Passagens separadas: atraso no 1º trecho não garante o 2º. "
                 "Bagagem é cobrada em cada bilhete.</i>")
    return "\n\n".join(parts)


def main(argv: list[str] | None = None) -> None:
    load_dotenv()
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    from .explore import _parse_range
    from .sources import get_source
    from .telegram import TelegramClient

    p = argparse.ArgumentParser(description="Relatório da estratégia de hub (2 passagens)")
    p.add_argument("origin")
    p.add_argument("dest")
    p.add_argument("depart", type=_parse_range, help="AAAA-MM-DD..AAAA-MM-DD")
    p.add_argument("nights", help="'10-15', '12' ou '-' pra só ida")
    p.add_argument("--hubs", default="", help="códigos separados por vírgula (vazio = candidatos da região)")
    p.add_argument("--source", default=os.environ.get("PRICE_SOURCE", "fastflights"))
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args(argv)

    rad = None
    if args.nights != "-":
        lo, _, hi = args.nights.partition("-")
        rad = (int(lo), int(hi or lo))
    route = RouteQuery(name=f"{args.origin}→{args.dest}", origin=args.origin.upper(),
                       dest=args.dest.upper(), depart_range=args.depart, return_after_days=rad)
    hubs = [h.strip().upper() for h in args.hubs.split(",") if h.strip()] or None
    text = hubs_report(get_source(args.source), route, hubs)
    print(text)
    if not args.dry_run:
        TelegramClient().send_message(text)


if __name__ == "__main__":
    main()
