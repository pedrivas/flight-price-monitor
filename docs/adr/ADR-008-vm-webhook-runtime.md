# ADR-008: Always-On Runtime on the Oracle VM, via Webhook

**Status:** Accepted
**Date:** 2026-09-28
**Supersedes:** ADR-006

## Context

ADR-006 already named an always-on host as the "graduation path" if GitHub
Actions cron latency became annoying. It did: right after that change the
`*/15` cron didn't fire for over an hour, and even the loosened `7,27,47 * * * *`
schedule is best-effort — GitHub throttles frequent schedules, and every run
still pays ~40s of checkout/pip setup before doing anything.

The graduation path now has somewhere to land: `vm-infra-oracle` runs a
production Traefik v3 edge with Let's Encrypt on the `market-store-oracle`
Always Free VM (`167-234-239-28.sslip.io`), and `horai-demo` already proves the
onboarding pattern with an exact-path webhook (`/webhook/horai-wa`). Joining
that platform costs no new VM, no new domain, no new firewall rule — just this
project's own `docker-compose.yml` on the shared `edge` network, per
`vm-infra-oracle/docs/onboarding-a-project.md`.

## Decision

Replace the GitHub Actions tick with a **single long-running process**
(`python -m monitor.server`, stdlib only — `http.server`, `threading`,
`queue`) in a container on the VM, reachable only through the shared Traefik
edge at an exact path (`/webhook/flight-tg`):

- **Telegram webhook**, not polling. The HTTP handler validates
  `X-Telegram-Bot-Api-Secret-Token`, dedupes by `update_id` against the
  existing `kv['telegram_offset']`, enqueues, and returns 200 immediately —
  before doing any work, so Telegram never times out and retries.
- **Two workers, two `Storage` connections.** A fast worker answers chat
  commands; a slow worker runs the price sweep, `/explorar`, and the daily
  backup. One `/explorar` (minutes) never delays a `/monitorias` reply.
  SQLite WAL + `busy_timeout=5000` (added to `Storage.__init__`) let both
  connections write to the same file without "database is locked".
- **The 6h sweep gate doesn't change** — `hours_since_last_sweep()` /
  `mark_sweep_done()` are exactly what they were; only the caller changes,
  from a GitHub cron tick to an in-process scheduler thread ticking every 60s.
- **`/explorar` becomes a real chat command** (see the 2026-09-28 note on
  ADR-007) instead of a separate `workflow_dispatch` — the queue/worker
  infrastructure this runtime needs anyway makes that free.
- **Daily backup to OCI Object Storage** via a pre-authenticated request (PUT
  URL) — no OCI SDK, no API key. Optional: unset `OCI_BACKUP_PAR_URL` and it
  just logs and skips, so the webhook cutover doesn't depend on the bucket
  existing yet.
- `history.db` leaves git and lives in `./data/` on the VM (onboarding rule
  8), so the VM's own filesystem — not commits — is now the source of truth.
  GitHub Actions keeps only `ci.yml`.

## Consequences

**Positive:**
- Commands answer in under a second instead of 0–20+ min best-effort.
- The sweep runs at a predictable time instead of whenever a cron slot lands.
- Reuses almost everything: `bot.handle_message`/`dispatch_message`,
  `main.run_sweep`, `explore.run_explore`, `Storage`'s kv/gate methods,
  `TelegramClient.send_message`. No new framework, no new dependency.
- Still R$ 0: the container is ~100–150 MB on a VM with 6 GB free of headroom,
  and it doesn't need a VM of its own.

**Negative:**
- A real host to keep alive now exists for this project, even if it's shared
  and already running. `docker compose up` on that VM is a step that can fail
  in ways a GitHub-hosted runner never could (disk, OOM from a neighboring
  project, a bad image).
- The webhook is new public attack surface, mitigated but not eliminated by
  the secret-token check and the existing chat allowlist.
- `fast-flights`' dependency on `primp` (Rust) needs an aarch64 wheel on this
  VM's A1 shape — validated before cutover (`docker compose run --rm app
  python -m monitor.main --sweep-now --dry-run --no-bot`), not assumed.
- One more repo (`vm-infra-oracle`) is now a dependency of this one being
  reachable — if its Traefik edge goes down, so does the webhook (the sweep
  and backup keep running either way; only inbound commands are affected).

## Alternatives Considered

- **Keep GitHub Actions, accept the latency** — rejected. ADR-006 already
  named this as the trigger to move on, and it happened.
- **Long-polling on the VM, no webhook** — rejected. Works, but a webhook is
  strictly better once a public HTTPS endpoint already exists for free: no
  polling loop hitting Telegram's API, no `getUpdates` timeout tuning, instant
  delivery instead of a poll interval.
- **Cloudflare Workers webhook** (ADR-006's other alternative) — rejected now
  that a VM with spare capacity and a working edge already exists; would add a
  second cloud account and runtime for no benefit over using the one already
  in place.
