from .base import PriceSource
from .fake import FakeSource
from .fastflights import FastFlightsSource
from .travelpayouts import TravelpayoutsSource

SOURCES = {
    "fastflights": FastFlightsSource,   # Google Flights ao vivo, sem cadastro (uso pessoal)
    "travelpayouts": TravelpayoutsSource,  # esboço: precisa de conta de afiliado
    "fake": FakeSource,                 # dados sintéticos p/ testar o pipeline
}


def get_source(name: str) -> PriceSource:
    try:
        return SOURCES[name]()
    except KeyError:
        raise SystemExit(f"Fonte desconhecida: {name}. Disponíveis: {', '.join(SOURCES)}")
