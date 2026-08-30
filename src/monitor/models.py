from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


@dataclass
class RouteQuery:
    """Uma rota a monitorar, vinda do routes.yaml."""

    name: str
    origin: str
    dest: str
    depart_range: tuple[date, date]
    adults: int = 1
    return_after_days: tuple[int, int] | None = None
    target_price: float | None = None
    drop_pct: float | None = None
    nonstop: bool = False
    currency: str = "BRL"

    @property
    def key(self) -> str:
        """Identificador estável da rota (usado no histórico e dedupe)."""
        rt = "ow" if self.return_after_days is None else f"{self.return_after_days[0]}-{self.return_after_days[1]}"
        return f"{self.origin}-{self.dest}-{rt}-{self.adults}p"


@dataclass
class Offer:
    """Uma oferta de passagem concreta retornada por uma fonte."""

    route_key: str
    price: float
    currency: str
    depart_date: date
    return_date: date | None
    carrier: str
    stops: int
    deep_link: str | None = None
    raw: dict = field(default_factory=dict)
