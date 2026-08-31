# ADR-006: Interactive Bot via Polling in the Existing Workflow

**Status:** Accepted
**Date:** 2026-08-31
**Supersedes:** ADR-004

## Context

ADR-004 chose GitHub Actions cron as the scheduler because the tool only needed
to *run* every few hours — no server, no cost.

The requirement changed: the user wants to manage monitored routes from Telegram
(`/monitorias`, `/criar`, `/editar`, `/excluir`). An interactive bot has to
*receive* messages — either long-polling (a process staying connected) or a
webhook (an HTTPS endpoint). Cron does neither.

Two facts shape the decision:
- Route management is **occasional** (set up a trip watch, tweak a target, delete
  when booked). A few minutes of latency is acceptable.
- The repo is **public**, so GitHub Actions minutes are unlimited and free.

## Decision

Keep everything in **one GitHub Actions workflow**, but run it **every 15 minutes**
instead of every 6 hours. Each run (`python -m monitor.main`, a "tick"):

1. `poll_and_handle` — one `getUpdates` call; execute any pending commands, reply.
2. If `hours_since_last_sweep() >= 6` → run the price sweep + alerts, then stamp
   `last_sweep_at`.
3. The workflow commits `data/history.db` back (unchanged from ADR-004).

Route state moves from `config/routes.yaml` into a **`routes` table** in the same
SQLite file. `config/routes.yaml` becomes a one-time **seed** (imported only when
the table is empty). The Telegram update offset and the sweep timestamp live in a
`kv` table.

Price-history keys switch from a derived string (`GRU-BEL-7-21-1p`) to the row id
(`r7`), so editing a route's target/name/dates keeps its history.

Command parsing is deliberately minimal: one-line syntax, hand-rolled parser, no
`python-telegram-bot` dependency. Only messages from `TELEGRAM_ALLOWED_CHAT_IDS`
(default: `TELEGRAM_CHAT_ID`) are acted on.

## Consequences

**Positive:**
- Still zero infra, zero cost. No new account, one language, one repo.
- Command latency 0–15 min — fine for the interaction frequency.
- Single writer to the SQLite file (one workflow), so no commit races.
- The command handler (`bot.handle_message`) is pure and unit-tested; only the
  transport would change if we ever move to a webhook.

**Negative:**
- The Actions tab gets ~96 runs/day (filterable, but noisy).
- GitHub throttles frequent schedules on free runners — effective cadence may be
  15–25 min at peak.
- `routes.yaml` is no longer the source of truth once the DB is seeded; it can
  drift from reality. It stays as documentation / disaster-recovery seed.
- Pre-existing history under the old string keys is orphaned (days of test data,
  no real baseline lost).

## Alternatives Considered

- **Always-on process on a host** (unified `python-telegram-bot` + APScheduler on
  Fly.io / Oracle Cloud Always Free / a Raspberry Pi). Best UX (instant replies).
  Rejected for now: needs a machine running 24/7 and breaks the zero-infra
  property for a feature used a few times a week. This is the natural graduation
  path if the 15-min latency becomes annoying.
- **Cloudflare Workers webhook + D1/KV.** Instant, free, no 24/7 host. Rejected:
  splits state to Cloudflare, adds a second language/runtime and account for a
  small tool. Kept as a fallback.
- **Second workflow just for the bot.** Rejected: two writers to `history.db`
  race on the binary file; merging one workflow is simpler.
