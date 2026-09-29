from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date

from ..models import Offer, RouteQuery


class PriceSource(ABC):
    """Interface de uma fonte de preços. Troque a fonte implementando `search`
    (e `quote`, se ela for usada na estratégia de hub)."""

    name: str = "base"

    @abstractmethod
    def search(self, route: RouteQuery) -> list[Offer]:
        """Retorna as ofertas encontradas para a rota (pode ser lista vazia)."""
        raise NotImplementedError

    def quote(
        self,
        origin: str,
        dest: str,
        depart: date,
        return_date: date | None = None,
        *,
        adults: int = 1,
        currency: str = "BRL",
        nonstop: bool = False,
        route_key: str = "",
    ) -> list[Offer]:
        """Uma consulta com datas fixas (só ida se `return_date` for None).

        `search` sorteia as datas sozinho; a estratégia de hub precisa
        controlar a data de cada trecho pra garantir a folga no hub — por isso
        existe esta chamada de baixo nível. Fonte que não implementa fica fora
        da estratégia de hub (o hub loga e pula, não quebra a varredura).
        """
        raise NotImplementedError(f"fonte {self.name} não suporta consulta por data (quote)")
