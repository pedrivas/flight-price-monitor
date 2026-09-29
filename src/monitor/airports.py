"""Mapa estático aeroporto -> (cidade, país, região). Cobre os destinos usados
no projeto (routes.yaml, explore.DEFAULT_DESTS, monitorias, candidatos a hub)
— não é uma base IATA completa. Destino fora do mapa cai no fallback (mostra
o próprio código, sem quebrar).

Região escolhe os candidatos a hub (hubs.HUB_CANDIDATES): "br", "sa"
(América do Sul), "na" (América do Norte/Central), "eu" (Europa +
Mediterrâneo), "me" (Oriente Médio), "asia", "af" (África), "oc" (Oceania).
"""
from __future__ import annotations

AIRPORTS: dict[str, tuple[str, str, str]] = {
    # Brasil — origem
    "GRU": ("São Paulo", "Brasil", "br"), "CGH": ("São Paulo", "Brasil", "br"),
    "VCP": ("São Paulo", "Brasil", "br"), "SAO": ("São Paulo", "Brasil", "br"),
    # Brasil — destinos
    "REC": ("Recife", "Brasil", "br"), "SSA": ("Salvador", "Brasil", "br"),
    "FOR": ("Fortaleza", "Brasil", "br"), "NAT": ("Natal", "Brasil", "br"),
    "MCZ": ("Maceió", "Brasil", "br"), "JPA": ("João Pessoa", "Brasil", "br"),
    "SLZ": ("São Luís", "Brasil", "br"), "BEL": ("Belém", "Brasil", "br"),
    "POA": ("Porto Alegre", "Brasil", "br"), "CWB": ("Curitiba", "Brasil", "br"),
    "FLN": ("Florianópolis", "Brasil", "br"), "IGU": ("Foz do Iguaçu", "Brasil", "br"),
    "BSB": ("Brasília", "Brasil", "br"), "CNF": ("Belo Horizonte", "Brasil", "br"),
    "GIG": ("Rio de Janeiro", "Brasil", "br"), "VIX": ("Vitória", "Brasil", "br"),
    "CGB": ("Cuiabá", "Brasil", "br"), "GYN": ("Goiânia", "Brasil", "br"),
    "BPS": ("Porto Seguro", "Brasil", "br"), "IOS": ("Ilhéus", "Brasil", "br"),
    # América do Sul
    "EZE": ("Buenos Aires", "Argentina", "sa"), "SCL": ("Santiago", "Chile", "sa"),
    "MVD": ("Montevidéu", "Uruguai", "sa"), "ASU": ("Assunção", "Paraguai", "sa"),
    "LIM": ("Lima", "Peru", "sa"), "BOG": ("Bogotá", "Colômbia", "sa"),
    "MDE": ("Medellín", "Colômbia", "sa"),
    # América do Norte / Central
    "MIA": ("Miami", "EUA", "na"), "FLL": ("Fort Lauderdale", "EUA", "na"),
    "MCO": ("Orlando", "EUA", "na"), "JFK": ("Nova York", "EUA", "na"),
    "PTY": ("Cidade do Panamá", "Panamá", "na"), "CUN": ("Cancún", "México", "na"),
    # Europa + Mediterrâneo
    "LIS": ("Lisboa", "Portugal", "eu"), "OPO": ("Porto", "Portugal", "eu"),
    "MAD": ("Madri", "Espanha", "eu"), "BCN": ("Barcelona", "Espanha", "eu"),
    "FCO": ("Roma", "Itália", "eu"), "MXP": ("Milão", "Itália", "eu"),
    "CDG": ("Paris", "França", "eu"), "LHR": ("Londres", "Reino Unido", "eu"),
    "FRA": ("Frankfurt", "Alemanha", "eu"), "AMS": ("Amsterdã", "Holanda", "eu"),
    "ATH": ("Atenas", "Grécia", "eu"), "TIA": ("Tirana", "Albânia", "eu"),
    "IST": ("Istambul", "Turquia", "eu"),
    "TBS": ("Tbilisi", "Geórgia", "eu"), "BUS": ("Batumi", "Geórgia", "eu"),
    # Oriente Médio
    "DOH": ("Doha", "Catar", "me"), "DXB": ("Dubai", "Emirados", "me"),
    # Ásia
    "HAN": ("Hanói", "Vietnã", "asia"), "SGN": ("Ho Chi Minh City", "Vietnã", "asia"),
    "MNL": ("Manila", "Filipinas", "asia"), "BKK": ("Bangkok", "Tailândia", "asia"),
    "NRT": ("Tóquio", "Japão", "asia"),
    # África
    "CAI": ("Cairo", "Egito", "af"), "CMN": ("Casablanca", "Marrocos", "af"),
    "ADD": ("Adis Abeba", "Etiópia", "af"), "JNB": ("Joanesburgo", "África do Sul", "af"),
    # Oceania
    "SYD": ("Sydney", "Austrália", "oc"),
}


def city_country(code: str) -> tuple[str, str]:
    """(cidade, país) pro código; sem entrada no mapa devolve (código, '—')."""
    city, country, _region = AIRPORTS.get(code.upper(), (code.upper(), "—", ""))
    return city, country


def region(code: str) -> str:
    """Região do aeroporto, ou '' se não estiver no mapa."""
    return AIRPORTS.get(code.upper(), ("", "", ""))[2]
