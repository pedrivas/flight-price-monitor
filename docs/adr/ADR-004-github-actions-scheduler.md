# ADR-004: GitHub Actions as Scheduler and History Store

**Status:** Superseded by [ADR-006](ADR-006-interactive-bot-and-polling-runtime.md)
**Date:** 2026-08-30

> The GitHub Actions + committed-SQLite model still holds. ADR-006 only changes
> the cadence (every 15 min instead of every 6h) and adds Telegram command
> handling to the same workflow.

## Context

The monitor must run unattended every few hours. It also needs its SQLite price
history (ADR-003) to survive between runs. This is a personal project with no
budget and no existing infrastructure.

## Decision

Run the monitor as a scheduled **GitHub Actions** workflow
(`.github/workflows/monitor.yml`), `cron: "17 */6 * * *"`, plus a manual
`workflow_dispatch` trigger.

Secrets (`TELEGRAM_*`, `TRAVELPAYOUTS_*`) are stored as Actions secrets. After
each run the workflow commits `data/history.db` back to the repo with a
`[skip ci]` message, so the next run restores the baseline via `checkout`.

## Consequences

**Positive:**
- Zero cost, zero servers. Free tier covers a 6-hour cadence comfortably.
- Secrets are managed by GitHub, never in the repo.
- History is versioned — every price observation is in git history.
- `workflow_dispatch` gives a one-click manual run.

**Negative:**
- The repo accumulates automated commits (mitigated: `[skip ci]`, single bot
  author, one file).
- A binary SQLite file in git is not diff-friendly and grows over time.
- Concurrent runs could race on the commit; `concurrency: monitor` serializes them.
- Cron timing on Actions is best-effort, not exact — fine for this use case.

## Alternatives Considered

- **Always-on VPS with system cron** — rejected. Recurring cost and patching
  burden for a job that runs seconds per invocation.
- **Serverless (Lambda / Cloud Run) + managed DB** — rejected. More moving parts
  and a cloud account for what a workflow file does.
- **Actions cache instead of committing the DB** — rejected. Cache eviction is
  not guaranteed; losing it silently resets the baseline.
- **External DB (Turso, Neon free tier)** — deferred. Reasonable upgrade if the
  committed-file approach becomes painful.
