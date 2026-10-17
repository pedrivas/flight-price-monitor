"""Preço + datas + links do último melhor achado de cada opção de uma rota.

Monta tudo a partir do `price_history` (Storage.last_observation), sem buscar
de novo: as datas dos bilhetes de uma opção via hub ou multidestino são
derivadas das mesmas regras que a busca usa (folga de LAYOVER_DAYS no hub;
ida em d e volta de `return_from` em d+N).
"""
from __future__ import annotations

import html
from datetime import timedelta

from .airports import city_country
from .hubs import LAYOVER_DAYS
from .models import RouteQuery
from .notifier import _flights_link, esc, multi_city_url
from .storage import Storage


def option_links(route: RouteQuery, route_key: str, dep, ret) -> list[tuple[str, str]]:
    """[(rótulo, url)] para comprar a opção gravada em `route_key`."""
    o, d = route.origin, route.dest
    if "@" in route_key:
        hub = route_key.split("@", 1)[1]
        gap = timedelta(days=LAYOVER_DAYS)
        if ret is None:
            return [(f"{o}→{hub}", _flights_link(o, hub, dep)), (f"{hub}→{d}", _flights_link(hub, d, dep + gap))]
        return [(f"{o}⇄{hub}", _flights_link(o, hub, dep, ret)),
                (f"{hub}⇄{d}", _flights_link(hub, d, dep + gap, ret - gap))]
    if route.return_from and ret is not None:
        back = route.return_from
        links = [(f"{o}→{d}", _flights_link(o, d, dep)), (f"{back}→{o}", _flights_link(back, o, ret))]
        multi = multi_city_url([(o, d, dep), (back, o, ret)], route.currency)
        if multi:
            links.append(("multidestino", multi))
        return links
    return [("Google Flights", _flights_link(o, d, dep, ret))]


def _anchors(links: list[tuple[str, str]]) -> str:
    return " · ".join(f'<a href="{html.escape(url, quote=True)}">{esc(label)}</a>' for label, url in links)


def option_line(storage: Storage, route: RouteQuery, route_key: str) -> str | None:
    """'via BCN: BRL 5000 · 31/05→14/06 · Avianca + SKY express · 🔗 SAO⇄BCN · BCN⇄ATH'."""
    obs = storage.last_observation(route_key)
    if obs is None:
        return None
    if "@" in route_key:
        label = f"via {route_key.split('@', 1)[1]}"
    elif route.return_from:
        label = f"ida {route.dest}, volta de {route.return_from}"
    else:
        label = "direto"
    dep, ret = obs["depart_date"], obs["return_date"]
    dates = f"{dep:%d/%m}" + (f"→{ret:%d/%m}" if ret else " (só ida)")
    return (f"{esc(label)}: {esc(obs['currency'])} {obs['price']:.0f} · {dates} · {esc(obs['carrier'])}"
            f" · 🔗 {_anchors(option_links(route, route_key, dep, ret))}")


def route_option_lines(storage: Storage, route: RouteQuery) -> list[str]:
    """Uma linha por opção com preço gravado: direto (ou multidestino) e cada hub."""
    keys = [route.key] + [f"{route.key}@{h}" for h in route.hubs]
    return [line for line in (option_line(storage, route, k) for k in keys) if line]


def sweep_summary(storage: Storage, alerts: int) -> str:
    """Resumo do /varrer: a melhor opção de cada monitoria, com datas e links."""
    routes = storage.list_routes(active_only=True)
    parts = [f"🔄 <b>Varredura concluída</b> · {len(routes)} monitoria(s) · {alerts} alerta(s)"]
    for r in routes:
        best, hub = storage.best_last_price(r)
        city, _ = city_country(r.dest)
        target = f" · alvo {r.target_price:.0f}" if r.target_price is not None else ""
        head = f"<b>#{r.id}</b> {esc(r.name)} ({esc(city)}){target}"
        line = option_line(storage, r, f"{r.key}@{hub}" if hub else r.key) if best is not None else None
        parts.append(head + "\n   " + (line or "sem preço nesta varredura"))
    return "\n\n".join(parts)
