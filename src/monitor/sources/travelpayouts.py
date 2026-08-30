from __future__ import annotations

import hashlib
import os
import time
from datetime import date, timedelta

import requests

from ..models import Offer, RouteQuery
from .base import PriceSource

# ---------------------------------------------------------------------------
# ATENÇÃO: esboço NÃO testado. Precisa de conta de afiliado Travelpayouts
# (marker + token). Confira os endpoints/campos na doc antes de usar:
# https://support.travelpayouts.com/hc/en-us/articles/30565016140434
#
# Fluxo: POST inicia a busca -> devolve search_id/uuid -> faz polling dos
# resultados até parar de chegar coisa nova (ou ~15 min de janela).
# ---------------------------------------------------------------------------

START_URL = "https://api.travelpayouts.com/v1/flight_search"
RESULTS_URL = "https://api.travelpayouts.com/v1/flight_search_results"


def _signature(token: str, marker: str, params: dict) -> str:
    """Assinatura MD5 da Travelpayouts: token:marker:<valores ordenados por chave>.
    Para dicts aninhados (passengers, segments) os valores entram na ordem em
    que a doc especifica — revise contra a doc oficial."""
    def flatten(value):
        if isinstance(value, dict):
            return [flatten(value[k]) for k in sorted(value)]
        if isinstance(value, (list, tuple)):
            return [flatten(v) for v in value]
        return str(value)

    flat: list[str] = []

    def walk(v):
        f = flatten(v)
        if isinstance(f, list):
            for x in f:
                walk(x)
        else:
            flat.append(f)

    for key in sorted(params):
        walk(params[key])

    raw = ":".join([token, marker, *flat])
    return hashlib.md5(raw.encode()).hexdigest()


class TravelpayoutsSource(PriceSource):
    name = "travelpayouts"

    def __init__(self) -> None:
        self.token = os.environ["TRAVELPAYOUTS_TOKEN"]
        self.marker = os.environ["TRAVELPAYOUTS_MARKER"]
        self.user_ip = os.environ.get("TRAVELPAYOUTS_USER_IP", "127.0.0.1")

    def search(self, route: RouteQuery) -> list[Offer]:
        offers: list[Offer] = []
        for dep in _sample_dates(*route.depart_range):
            segments = [{"origin": route.origin, "destination": route.dest, "date": dep.isoformat()}]
            ret: date | None = None
            if route.return_after_days:
                lo, hi = route.return_after_days
                ret = dep + timedelta(days=(lo + hi) // 2)
                segments.append({"origin": route.dest, "destination": route.origin, "date": ret.isoformat()})

            body = {
                "marker": self.marker,
                "host": "flight-price-monitor.local",
                "user_ip": self.user_ip,
                "locale": "pt-BR",
                "trip_class": "Y",
                "passengers": {"adults": route.adults, "children": 0, "infants": 0},
                "segments": segments,
            }
            body["signature"] = _signature(self.token, self.marker, body)

            r = requests.post(START_URL, json=body, timeout=30)
            r.raise_for_status()
            search_id = r.json().get("search_id") or r.json().get("uuid")
            if not search_id:
                continue

            for offer in self._poll(search_id, route, dep, ret):
                offers.append(offer)
            time.sleep(1)
        return offers

    def _poll(self, search_id: str, route: RouteQuery, dep: date, ret: date | None):
        for _ in range(10):
            time.sleep(3)
            r = requests.get(RESULTS_URL, params={"uuid": search_id}, timeout=30)
            r.raise_for_status()
            chunks = r.json()
            done = False
            for chunk in chunks:
                for proposal in chunk.get("proposals", []):
                    price = proposal.get("unified_price") or proposal.get("price")
                    if not price:
                        continue
                    yield Offer(
                        route_key=route.key,
                        price=float(price),
                        currency=route.currency,
                        depart_date=dep,
                        return_date=ret,
                        carrier=proposal.get("validating_carrier", "??"),
                        stops=max((len(seg.get("flight", [])) - 1) for seg in proposal.get("segment", [{}])),
                        raw=proposal,
                    )
                if not chunk.get("proposals"):
                    done = True
            if done:
                break


def _sample_dates(start: date, end: date, max_samples: int = 4) -> list[date]:
    span = (end - start).days
    if span <= 0:
        return [start]
    step = max(1, span // max_samples)
    return [start + timedelta(days=d) for d in range(0, span + 1, step)][:max_samples]
