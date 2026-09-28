"""Mapa estático aeroporto -> (cidade, país). Cobre os destinos usados no
projeto (routes.yaml, explore.DEFAULT_DESTS, monitorias criadas via bot) —
não é uma base IATA completa. Destino fora do mapa cai no fallback (mostra
o próprio código, sem quebrar)."""
from __future__ import annotations

AIRPORTS: dict[str, tuple[str, str]] = {
    # Brasil — origem
    "GRU": ("São Paulo", "Brasil"), "CGH": ("São Paulo", "Brasil"),
    "VCP": ("São Paulo", "Brasil"), "SAO": ("São Paulo", "Brasil"),
    # Brasil — destinos
    "REC": ("Recife", "Brasil"), "SSA": ("Salvador", "Brasil"), "FOR": ("Fortaleza", "Brasil"),
    "NAT": ("Natal", "Brasil"), "MCZ": ("Maceió", "Brasil"), "JPA": ("João Pessoa", "Brasil"),
    "SLZ": ("São Luís", "Brasil"), "BEL": ("Belém", "Brasil"), "POA": ("Porto Alegre", "Brasil"),
    "CWB": ("Curitiba", "Brasil"), "FLN": ("Florianópolis", "Brasil"), "IGU": ("Foz do Iguaçu", "Brasil"),
    "BSB": ("Brasília", "Brasil"), "CNF": ("Belo Horizonte", "Brasil"), "GIG": ("Rio de Janeiro", "Brasil"),
    "VIX": ("Vitória", "Brasil"), "CGB": ("Cuiabá", "Brasil"), "GYN": ("Goiânia", "Brasil"),
    "BPS": ("Porto Seguro", "Brasil"), "IOS": ("Ilhéus", "Brasil"),
    # América do Sul
    "EZE": ("Buenos Aires", "Argentina"), "SCL": ("Santiago", "Chile"),
    "MVD": ("Montevidéu", "Uruguai"), "ASU": ("Assunção", "Paraguai"),
    "LIM": ("Lima", "Peru"), "BOG": ("Bogotá", "Colômbia"), "MDE": ("Medellín", "Colômbia"),
    # Intercontinental
    "CAI": ("Cairo", "Egito"), "HAN": ("Hanói", "Vietnã"), "SGN": ("Ho Chi Minh City", "Vietnã"),
    "MNL": ("Manila", "Filipinas"), "BKK": ("Bangkok", "Tailândia"), "IST": ("Istambul", "Turquia"),
    "LIS": ("Lisboa", "Portugal"), "CMN": ("Casablanca", "Marrocos"), "TIA": ("Tirana", "Albânia"),
    "TBS": ("Tbilisi", "Geórgia"), "BUS": ("Batumi", "Geórgia"),
}


def city_country(code: str) -> tuple[str, str]:
    """(cidade, país) pro código; sem entrada no mapa devolve (código, '—')."""
    return AIRPORTS.get(code.upper(), (code.upper(), "—"))
