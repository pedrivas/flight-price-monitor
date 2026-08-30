# ADR-002: Pluggable Price Source Interface

**Status:** Accepted
**Date:** 2026-08-30

## Context

Free flight-data providers are unstable: they shut down (ADR-001), change auth,
or degrade. The tool must not be rewritten each time the data source changes.

The downstream logic — history, baseline, alert rules, Telegram delivery — is
identical regardless of where a price came from.

## Decision

Define a single abstract collector:

```python
class PriceSource(ABC):
    @abstractmethod
    def search(self, route: RouteQuery) -> list[Offer]: ...
```

- `RouteQuery` and `Offer` are plain dataclasses in `monitor.models`. `Offer` is
  the normalized unit every downstream stage consumes.
- Implementations live in `src/monitor/sources/` and are registered by name in
  `sources/__init__.py`.
- The active source is chosen at runtime via `PRICE_SOURCE` / `--source`.

Three implementations ship: `fastflights`, `travelpayouts` (draft), `fake`
(synthetic data for testing the pipeline offline).

## Consequences

**Positive:**
- Adding a source is one file + one registry line. Nothing downstream changes.
- The `fake` source makes the pipeline testable with no network and no keys.
- Source-specific concerns (async polling, signatures, rate limits) stay
  contained in that source.

**Negative:**
- The `Offer` model is a lowest common denominator. Source-specific richness
  (fare rules, baggage, deep links) is dropped or stuffed into `Offer.raw`.
- Each source re-implements date sampling; a shared helper would reduce
  duplication.

## Alternatives Considered

- **One hardcoded provider** — rejected. ADR-001 is the concrete reason: the
  original provider disappeared mid-project.
- **A generic HTTP config (declare endpoint + JSON paths in YAML)** — rejected.
  Real providers differ too much (async search sessions, HMAC signatures,
  pagination) to express declaratively without a config language as complex as code.
