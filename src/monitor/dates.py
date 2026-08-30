from __future__ import annotations

from datetime import date, timedelta


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
