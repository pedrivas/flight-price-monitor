from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import yaml

from .models import RouteQuery

CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "routes.yaml"


def _as_date(value) -> date:
    return value if isinstance(value, date) else date.fromisoformat(str(value))


def load_routes(path: Path = CONFIG_PATH) -> list[RouteQuery]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    currency = raw.get("currency", "BRL")
    routes: list[RouteQuery] = []
    for r in raw["routes"]:
        dr = r["depart_range"]
        rad = r.get("return_after_days")
        routes.append(
            RouteQuery(
                name=r["name"],
                origin=r["origin"].upper(),
                dest=r["dest"].upper(),
                depart_range=(_as_date(dr[0]), _as_date(dr[1])),
                adults=int(r.get("adults", 1)),
                return_after_days=(int(rad[0]), int(rad[1])) if rad else None,
                target_price=r.get("target_price"),
                drop_pct=r.get("drop_pct"),
                nonstop=bool(r.get("nonstop", False)),
                currency=currency,
            )
        )

    for route in routes:
        if route.target_price is None and route.drop_pct is None:
            print(
                f"[aviso] rota '{route.name}' não tem target_price nem drop_pct "
                f"— nunca vai gerar alerta",
                file=sys.stderr,
            )
    return routes
