# ADR-007: Explore as a Separate On-Demand Workflow

**Status:** Accepted
**Date:** 2026-09-01

## Context

The "explore" feature answers a different question than the monitor: *given an
origin, a departure window, a return window and a budget, which destinations fit?*
It sweeps a curated list of ~25 destinations, each a full `PriceSource.search`
(~4 sampled dates, retry-wrapped). That is ~100 live fetches, 5–10 minutes per run.

The monitor runs as a 15–20 min "tick" (ADR-006) that also handles Telegram
commands synchronously. Anything slow in that path blocks both the price sweep and
the bot.

## Decision

Ship explore as its own **`workflow_dispatch`** workflow (`explorar`), separate
from `monitor-passagens`:

- Typed inputs: origin, departure window, return window, max price, optional
  destination override.
- `timeout-minutes: 30`, its own `concurrency` group.
- No `contents: write`, no commit step — explore persists nothing.
- Posts the ranked result (under budget + a few near-misses) to the Telegram group.

The code (`monitor/explore.py`) reuses `FastFlightsSource` by looping it over one
synthetic `RouteQuery` per destination. The return *window* is collapsed to a
nights count (window-midpoint to window-midpoint) so `search()` is reused
unchanged — explore is discovery, not date-precise pricing.

It is **not** a chat command: a `/explorar` typed in the group would freeze the
tick for the whole sweep.

## Consequences

**Positive:**
- Zero impact on the monitor tick or bot latency.
- Stateless — nothing to migrate, nothing to commit, no schema.
- Reuses the collector's retry/parsing/currency handling.

**Negative:**
- Round trips are approximate on dates (one nights value, not the full window).
- The destination list is curated in code; broadening it means editing
  `DEFAULT_DESTS` (or passing `--destinations`).
- Triggered from the Actions UI / `gh`, not from Telegram.

## Alternatives Considered

- **`/explorar` bot command** — rejected. An 8-minute synchronous handler inside
  `poll_and_handle` blocks the tick.
- **Async job queue** (command enqueues, a later tick runs it, posts when done) —
  rejected as over-engineering for an occasional manual query.
- **Fold into the `monitor-passagens` `command` input** — rejected. Mixes a heavy,
  unrelated operation into the monitor workflow.
