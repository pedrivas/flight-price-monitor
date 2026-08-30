# ADR-005: LLM-Based Promo Classification — Deferred

**Status:** Accepted (deferred to a future version)
**Date:** 2026-08-30

## Context

This is an interview study for an AI Engineer role, so "where does an LLM belong
here?" is a question worth answering explicitly rather than by omission.

Candidate uses for an LLM in this tool:

1. **Promo classification** — decide whether a fare is a "genuine promotion"
   versus normal fluctuation, using context a threshold cannot see (route
   seasonality, how the fare compares to typical carriers, fare conditions).
2. **Natural-language route config** — "watch cheap flights to the Northeast in
   January" instead of editing YAML.
3. **Alert summarization / ranking** — one digest message ranking the day's
   findings with a short rationale.

## Decision

Ship v1 with **no LLM in the hot path**. Use the deterministic baseline + target
rules from ADR-003. Document the LLM integration point as future work.

The decision rule applied: an LLM earns its place when the task needs judgment
over unstructured or contextual input. Deciding `price <= threshold` does not.
Classifying "is this genuinely a good deal, given everything about this route"
plausibly does — but only once there is enough price history to give a model
meaningful context, and enough alert volume for precision to matter.

## Consequences

**Positive:**
- v1 is fully deterministic: testable, free, no latency, no API key, no failure mode.
- The `rules.py` boundary is a clean seam — an `LlmClassifier` becomes one more
  check in `evaluate()`, or a re-ranking pass over candidate alerts.
- Gives a concrete, honest interview answer: chose *not* to use AI where a
  heuristic suffices, and can articulate the threshold for revisiting.

**Negative:**
- The relative rule can still misfire on genuinely volatile routes; an LLM with
  route context might catch those. Accepted for now.

## Alternatives Considered

- **LLM classifier in v1** — rejected. No historical context to feed it yet, no
  alert-volume problem to solve, adds a key and a network dependency to a job
  that currently cannot fail.
- **LLM for NL route config** — deferred. Nice ergonomics, zero effect on alert
  quality; belongs in a later iteration.
- **Rules engine (JSON-logic style)** — rejected. More machinery than two
  conditions justify.
