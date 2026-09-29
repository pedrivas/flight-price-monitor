# Flight Price Monitor — CLAUDE.md

## Project overview

Personal tool that watches airfare for a set of routes and sends a Telegram
message when a fare hits a target price or drops sharply against its own history.

This project is a practical study for an AI Engineer interview. Each architectural
decision maps to a specific interview topic (see `docs/adr/` and the table below).
It deliberately ships **without** an LLM in the hot path — ADR-005 documents where
one would fit and why it was deferred.

## Architecture

A single long-running process (`python -m monitor.server`) on a VM, reached
through a Telegram **webhook** — not GitHub Actions cron anymore (ADR-008,
supersedes ADR-006):

```
Telegram ──HTTPS──▶ Traefik edge (vm-infra-oracle) ──▶ POST /webhook/flight-tg
                                                              │ valida secret, dedupe,
                                                              │ 200 na hora, enfileira
                                          ┌───────────────────┴───────────────────┐
                                    fila rápida                             fila lenta ◀── scheduler (tick 1/min)
                                          │                                        │
                              worker rápido (Storage própria)          worker lento (Storage própria)
                              handle_update → responde comandos        run_sweep / run_explore / backup
                                                                        Collector → Storage → Rules → Notifier
```

- The collector (`PriceSource`) is the only pluggable stage; everything
  downstream works on the normalized `Offer` model.
- **State lives in `./data/history.db`** on the VM (WAL mode — the two workers
  each hold their own connection): `price_history`, `alerts_sent`, `routes`,
  `kv` (Telegram offset, last-sweep timestamp, last-backup timestamp). It is
  **not** in git anymore — see `docs/adr/ADR-008-vm-webhook-runtime.md`.
- `config/routes.yaml` is a **one-time seed** for the `routes` table; after
  that the DB is the source of truth and routes are managed via the bot.
- Price-history key is the route row id (`r7`), so editing a route keeps its history.
  Hub options (two separate tickets via a hub, opt-in per route in `routes.hubs`)
  get their own key `r7@LIS`, so their baseline and dedupe never mix with the
  direct fare. The sweep sends at most one alert per route (ADR-009).
- Deploy platform: `vm-infra-oracle` (separate repo) — Traefik edge, exact-path
  routing, `docker-compose.yml` per project. This repo owns only its own compose
  file and follows `vm-infra-oracle/docs/onboarding-a-project.md`.

## Stack

- Python 3.10+ (standard library + `requests`, `PyYAML`, `python-dotenv`)
- `fast-flights` — live Google Flights data (default source)
- SQLite (WAL) — price history, route store, bot/scheduler state (no server)
- Telegram Bot API — webhook delivery + interactive route management
  (hand-rolled, no bot framework)
- `http.server`/`threading`/`queue` (stdlib only) — the webhook server, its two
  workers and the in-process scheduler (`monitor/server.py`)
- Docker Compose on a shared Oracle Cloud Always Free VM, behind a Traefik edge
  (`vm-infra-oracle`) — see ADR-008, supersedes ADR-006 (which supersedes ADR-004)
- GitHub Actions — CI only (`ci.yml`); no longer the runtime

## Running locally

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env        # fill in the Telegram values

export PYTHONPATH=src
python -m monitor.main --sweep-now --dry-run --source fake --no-bot  # smoke test, no network
python -m monitor.main --bot-only                # process Telegram commands (polling), no sweep
python -m monitor.main --sweep-now --dry-run     # real fares, nothing sent
python -m monitor.main                           # one tick: bot poll + sweep if due
python -m monitor.server                         # the real always-on runtime (webhook + workers + scheduler)
```

CLI flags on `main.py`: `--dry-run`, `--source`, `--sweep-now` (force sweep),
`--no-bot`, `--bot-only` (skip sweep), `--command "/excluir 3"` (run one bot
command and exit), `--backup-now` (force the OCI backup and exit).

`monitor.server` needs `TELEGRAM_WEBHOOK_SECRET` set and listens on
`0.0.0.0:${PORT:-8080}` — fine inside a container reached only through the
`edge` Docker network (see `docker-compose.yml`); don't run it bound to a
public interface outside a container. Locally, `--bot-only` polling is the
easier way to exercise `bot.py` without standing up the webhook.

**Docker:** `docker compose config -q` validates syntax; `docker compose run
--rm app python -m monitor.main --sweep-now --dry-run --no-bot` runs a real
sweep inside the image without starting the server — this is also the exact
command the cutover runbook uses to validate `fast-flights`' aarch64 wheel on
the VM before going live.

Tests: `pip install -r requirements-dev.txt && python -m pytest -q`
(pytest reads `pyproject.toml`, which puts `src/` on the path). `MONITOR_DB_PATH`
overrides the SQLite location — tests point it at a tmp file.

Routes: seeded from `config/routes.yaml` on first run, then managed via Telegram.
Dates must be in the future — Google Flights returns nothing for past dates.

## Conventions

- **Module structure:** `monitor.{config,models,storage,rules,notifier,telegram,bot,explore,hubs,airports,backup,server,main}`
  plus `monitor.sources.*` for collectors. `telegram` = thin Bot API client
  (`send_message`/`get_updates` for polling, `set_webhook`/`delete_webhook`/
  `get_webhook_info` for the webhook); `bot` = command parsing/handlers
  (`dispatch_message` is pure — `handle_message` is a thin wrapper that drops
  the `Job`; `handle_update` + `run_job` are what actually execute one); `explore`
  = the `/explorar` sweep, callable as a chat command or `python -m monitor.explore`
  (ADR-007, revisited by ADR-008); `backup` = the daily OCI Object Storage
  snapshot (optional — no-ops without `OCI_BACKUP_PAR_URL`); `server` = the
  webhook process (ADR-008) — HTTP handler, two workers, scheduler; `hubs` =
  split-ticket strategy (`search_via`, `discover`, the `/hubs` report, and
  `python -m monitor.hubs`), see ADR-009; `airports` = IATA code →
  (city, country, region) used by the table and the hub candidates.
- **Schema changes on an existing DB:** `CREATE TABLE IF NOT EXISTS` doesn't
  add columns. New `routes` columns go in `_ADDED_ROUTE_COLUMNS` in
  `storage.py`, which `ALTER TABLE`s them in on startup.
- **Pluggable sources:** a new price source implements `PriceSource.search()` in
  `src/monitor/sources/`, is registered in `sources/__init__.py`, and changes
  nothing downstream. See ADR-002. Optionally it also implements `quote()`, an
  exact origin/dest/date lookup that the hub strategy needs. Without it, hubs are
  skipped with a log line.
- **Environment variables are never hardcoded.** Read them via `os.environ` /
  `python-dotenv`. Secrets never land in the repo (`.env` is git-ignored).
- **Comments explain WHY, not WHAT.** Only add a comment when the reason for the
  code is non-obvious.
- **Conventional Commits:** `feat:`, `fix:`, `chore:`, `docs:`, `refactor:`.
- **ADRs** live in `docs/adr/`, named `ADR-{n}-{kebab-title}.md`. Create one for
  every significant architectural decision, including rejected ones.

## Environment variables

| Variable | Used by | Description |
|---|---|---|
| `PRICE_SOURCE` | `main` | Active collector: `fastflights` (default), `travelpayouts`, `fake` |
| `TELEGRAM_BOT_TOKEN` | `telegram` | Bot token from @BotFather |
| `TELEGRAM_CHAT_ID` | `telegram` | Alert destination + default allowed chat (see `scripts/get_chat_id.py`) |
| `TELEGRAM_ALLOWED_CHAT_IDS` | `bot` | Comma-separated chat ids allowed to run commands (optional; defaults to `TELEGRAM_CHAT_ID`) |
| `TRAVELPAYOUTS_TOKEN` | `travelpayouts` source | Affiliate API token (optional) |
| `TRAVELPAYOUTS_MARKER` | `travelpayouts` source | Affiliate marker / partner ID (optional) |
| `MONITOR_DB_PATH` | `storage` | Override the SQLite path (tests, local runs) |
| `TELEGRAM_WEBHOOK_SECRET` | `server` | Compared against `X-Telegram-Bot-Api-Secret-Token` on every POST; no secret = reject everything |
| `WEBHOOK_URL` | `scripts/set_webhook.py` | Full public webhook URL, e.g. `https://167-234-239-28.sslip.io/webhook/flight-tg` |
| `OCI_BACKUP_PAR_URL` | `backup` | Write Pre-Authenticated Request URL for the backup bucket (optional; unset = daily backup just logs and skips) |
| `PORT` | `server` | HTTP port inside the container (default `8080`) |
| `WEBHOOK_PATH` | `server` | Path the handler answers on (default `/webhook/flight-tg`) |

## Interview topics this project covers

| # | Topic | Where in the project |
|---|---|---|
| 1 | Technical Ownership | Every decision recorded in `docs/adr/` |
| 2 | Failure / adapting to change | ADR-001 — Amadeus Self-Service was decommissioned mid-build; the collector was re-pointed to `fast-flights` |
| 3 | Challenge the PM | ADR-002 rejects per-airline scraping; ADR-006 rejected an always-on host *until the constraint changed* — ADR-008 documents exactly when "no" should flip to "yes" |
| 4 | Architecture Document | `docs/adr/` + this file |
| 5 | Business Metrics | Alert precision (false positives), cost per run, route coverage — see ADR-003 |
| 6 | One Initiative + Metric | ADR-003 — historical baseline cuts noise alerts; metric = useful alerts / total alerts |
| 7 | AI-generated Code | Built with Claude Code; decisions reviewed through ADRs and PRs |
| 8 | Extensibility / Interface Design | ADR-002 — the `PriceSource` interface |
| 9 | Where AI fits (and where it doesn't) | ADR-005 — LLM-based promo classification evaluated and deferred |
| 10 | Test coverage of core logic | `tests/` — baseline/dedupe, alert rules, config, formatting, pipeline, route store, bot commands; CI on every push |
| 11 | Evolving under a new requirement | ADR-006 — interactive bot added by re-shaping the existing runtime, not rebuilding it; command handler is transport-agnostic |
| 12 | Where expensive work belongs | ADR-007/ADR-008 — the multi-minute explore sweep started as its own workflow (no worker to hand it to) and became a queued chat command once a long-running process existed |
| 13 | Deploying always-on infra | ADR-008 — webhook + two-worker/queue design, SQLite WAL for concurrent writers, graceful SIGTERM drain, joining a shared platform via a documented contract instead of standing up a new VM |
| 14 | Backup without a cloud SDK | `backup.py` — `sqlite3.Connection.backup()` + a plain HTTP PUT to a Pre-Authenticated Request URL; no OCI CLI, no API key, fails soft |
| 15 | Turning a manual insight into a product feature | ADR-009 — a one-off analysis (split tickets via Madrid beat direct to Athens) became an opt-in, per-route option. The first live test showed the saving disappears for round trips, which is why hubs are *discovered and verified* per route instead of hard-coded |
