# ADR-001: Live Price Source Selection

**Status:** Accepted
**Date:** 2026-08-30

## Context

The monitor needs real, current airfare data — not cached snapshots, since the
whole point is to catch a price the moment it drops.

The original design used the **Amadeus Self-Service API** (Flight Offers Search),
which offered a free tier with real GDS data. During development, Amadeus
**decommissioned the Self-Service developer portal on 2026-07-17**. Existing keys
were disabled; only the Enterprise API remains, which requires a commercial
contract and is not viable for a personal project.

This forced a reassessment of every free source of live fare data.

## Decision

Use a **pluggable collector** (see ADR-002) with two implementations:

1. **`fastflights` (default)** — the `fast-flights` library, which reads live
   Google Flights results. No signup, returns prices in the requested currency,
   covers effectively every route. It is unofficial and can break when Google
   changes its front-end; acceptable for a personal tool.
2. **`travelpayouts` (fallback)** — the Aviasales real-time search API, available
   with a free affiliate account. More stable and sanctioned, but requires a
   `marker` + `token` and a two-step async search flow.

The default is `fastflights` because it works with zero configuration. If it
breaks, switching sources is a one-line config change.

## Consequences

**Positive:**
- Zero-cost, zero-signup path to live data.
- Source outages are survivable — `PRICE_SOURCE` swaps the collector without
  touching storage, rules, or delivery.

**Negative:**
- `fast-flights` has no stability guarantee; a Google change can require waiting
  for a library patch.
- Round-trip results report only the outbound leg's stop count.
- No booking deep link — alerts link to a Google Flights search instead.

## Alternatives Considered

- **Amadeus Enterprise / Amadeus Quick Connect** — rejected. Requires a sales
  contract and onboarding meant for travel businesses at scale.
- **Duffel** — rejected. Sandbox returns synthetic data; production access
  requires being a verified travel seller.
- **Travelpayouts cached Data API** — rejected as the primary source. Data is
  aggregated from past searches and can be hours to days stale, which defeats a
  price-drop trigger. Kept in mind only as a coarse signal.
- **Per-airline scraping / unofficial endpoints** — rejected. One brittle
  integration per carrier, heavy anti-bot friction, no aggregation.
- **Paid APIs (FlightAPI.io, FlightLabs)** — rejected for a personal project;
  free tiers are trial-only (20–100 calls).
