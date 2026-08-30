from __future__ import annotations

from dataclasses import dataclass

from .models import Offer, RouteQuery
from .storage import Storage


@dataclass
class AlertDecision:
    should_alert: bool
    reasons: list[str]
    baseline: float | None


def evaluate(route: RouteQuery, offer: Offer, storage: Storage) -> AlertDecision:
    """Decide se a oferta merece um alerta."""
    reasons: list[str] = []
    baseline = storage.median_last_days(offer.route_key, days=30)

    if route.target_price is not None and offer.price <= route.target_price:
        reasons.append(f"preço {offer.price:.0f} ≤ alvo {route.target_price:.0f}")

    if route.drop_pct is not None and baseline:
        threshold = baseline * (1 - route.drop_pct / 100)
        if offer.price <= threshold:
            pct = (1 - offer.price / baseline) * 100
            reasons.append(f"queda de {pct:.0f}% vs. mediana 30d ({baseline:.0f})")

    if not reasons:
        return AlertDecision(False, [], baseline)

    if storage.already_alerted(offer.route_key, offer.price):
        return AlertDecision(False, ["já alertado recentemente"], baseline)

    return AlertDecision(True, reasons, baseline)
