from __future__ import annotations

from datetime import date, timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .models import RouteQuery


def sample_dates(start: date, end: date, max_samples: int = 4) -> list[date]:
    """Datas uniformemente espaçadas dentro de [start, end], incluindo as pontas.

    Mantém o número de buscas por rota baixo. Para janelas curtas devolve menos
    que `max_samples` (sem datas repetidas).
    """
    span = (end - start).days
    if span <= 0 or max_samples <= 1:
        return [start]
    step = span / (max_samples - 1)
    picked = {start + timedelta(days=round(i * step)) for i in range(max_samples)}
    return sorted(picked)


def trip_for(route: "RouteQuery", dep: date) -> tuple[date, date | None] | None:
    """(ida, volta) testada para uma data de ida, ou None se não cabe.

    Sem `return_by`: ponto médio da faixa de noites (uma duração só por data,
    pra não multiplicar buscas). Com `return_by` ("volta até"): a viagem mais
    longa da faixa que ainda volta até essa data — ida cedo ganha viagem
    longa, ida tarde encurta; se nem o mínimo de noites cabe, a data sai."""
    if not route.return_after_days:
        return dep, None
    lo, hi = route.return_after_days
    if route.return_by is None:
        return dep, dep + timedelta(days=(lo + hi) // 2)
    nights = min(hi, (route.return_by - dep).days)
    if nights < lo:
        return None
    return dep, dep + timedelta(days=nights)


def sample_trips(route: "RouteQuery", max_samples: int = 4) -> list[tuple[date, date | None]]:
    """Datas de ida amostradas + a volta de cada uma (ver trip_for). Com
    `return_by`, a janela de ida é cortada antes de amostrar, pra nenhuma
    amostra cair numa data que não cabe."""
    start, end = route.depart_range
    if route.return_by is not None and route.return_after_days:
        end = min(end, route.return_by - timedelta(days=route.return_after_days[0]))
        if end < start:
            return []
    trips = [trip_for(route, d) for d in sample_dates(start, end, max_samples)]
    return [t for t in trips if t is not None]
