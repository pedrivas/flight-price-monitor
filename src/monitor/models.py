from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


@dataclass
class RouteQuery:
    """Uma rota a monitorar. Vem da tabela `routes` (ou do routes.yaml no seed)."""

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
    id: int | None = None
    active: bool = True

    @property
    def key(self) -> str:
        """Identificador estável da rota (usado no histórico e no dedupe).

        Com id no banco a chave é `r<id>`, então editar alvo/nome/datas preserva
        o histórico. Sem id (rota só do YAML / testes) cai na string derivada.
        """
        if self.id is not None:
            return f"r{self.id}"
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
