# ADR-003: Historical Baseline Alerting and Dedupe

**Status:** Accepted
**Date:** 2026-08-30

## Context

A naive monitor alerts whenever `price <= target`. This has two failure modes:

- **Miss:** a route that is normally R$ 3,000 drops to R$ 2,100 — a real promo —
  but the target was set at R$ 2,000, so nothing fires.
- **Spam:** once a fare is below target, every run re-alerts the same fare.

The business metric for this tool is *useful alerts / total alerts*. Both failure
modes push that ratio down.

## Decision

Persist every observed cheapest fare per route in SQLite, and alert on either
condition:

1. `price <= target_price` (absolute floor the user cares about), **or**
2. `price <= median(last 30 days) * (1 - drop_pct/100)` (relative drop vs. the
   route's own recent history).

Deduplicate: a route is not re-alerted if a fare within 2% was already alerted in
the last 7 days (`alerts_sent` table).

Baseline uses **median**, not mean — fare distributions are right-skewed and a
single expensive scrape should not move the reference.

## Consequences

**Positive:**
- Catches real drops even when the absolute target is conservative.
- The 30-day window adapts as seasonal pricing shifts.
- Dedupe makes a 6-hour schedule safe — no alert fatigue.

**Negative:**
- The relative rule is dead until ~2–4 weeks of history exist. Absolute target
  covers the cold-start period.
- History lives in a committed SQLite file (ADR-004); a rebased or lost file
  resets the baseline.
- 2% / 7-day dedupe thresholds are hardcoded heuristics, not tuned against data yet.

## Alternatives Considered

- **Absolute target only** — rejected. Misses the most interesting drops and
  spams once under target.
- **Alert on any decrease vs. last run** — rejected. Too noisy; normal fare
  fluctuation would fire constantly.
- **Store full offer lists, not just the cheapest** — deferred. Larger history
  for marginal gain; the cheapest fare is what drives the decision.
