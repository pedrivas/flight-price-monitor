from __future__ import annotations

from abc import ABC, abstractmethod

from ..models import Offer, RouteQuery


class PriceSource(ABC):
    """Interface de uma fonte de preços. Troque a Amadeus por outra
    implementando só este método."""

    name: str = "base"

    @abstractmethod
    def search(self, route: RouteQuery) -> list[Offer]:
        """Retorna as ofertas encontradas para a rota (pode ser lista vazia)."""
        raise NotImplementedError
