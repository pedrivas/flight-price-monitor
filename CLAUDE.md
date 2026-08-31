# Flight Price Monitor — CLAUDE.md

## Project overview

Personal tool that watches airfare for a set of routes and sends a Telegram
message when a fare hits a target price or drops sharply against its own history.

This project is a practical study for an AI Engineer interview. Each architectural
decision maps to a specific interview topic (see `docs/adr/` and the table below).
It deliberately ships **without** an LLM in the hot path — ADR-005 documents where
one would fit and why it was deferred.

## Architecture

One GitHub Actions workflow runs `python -m monitor.main` — a "tick" — every
~20 minutes (ADR-006):

```
tick (every ~20 min, best-effort)
 ├─ bot.poll_and_handle   — Telegram getUpdates → /monitorias /criar /editar /excluir
 └─ if ≥6h since last sweep:
        Collector (PriceSource)  →  Storage (SQLite)  →  Rules  →  Notifier (Telegram)
```

- The collector is the only pluggable stage; everything downstream works on the
  normalized `Offer` model.
- **State lives in `data/history.db`** (committed back by the workflow): tables
  `price_history`, `alerts_sent`, `routes`, `kv` (Telegram offset + last-sweep
  timestamp).
- `config/routes.yaml` is a **one-time seed** for the `routes` table; after that
  the DB is the source of truth and routes are managed via the bot.
- Price-history key is the route row id (`r7`), so editing a route keeps its history.

## Stack

- Python 3.10+ (standard library + `requests`, `PyYAML`, `python-dotenv`)
- `fast-flights` — live Google Flights data (default source)
- SQLite — price history, route store, bot state (no server)
- Telegram Bot API — delivery + interactive route management (hand-rolled, no lib)
- GitHub Actions — the ~20-min tick and state persistence (see ADR-006, supersedes ADR-004)

## Running locally

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env        # fill in the Telegram values

export PYTHONPATH=src
python -m monitor.main --sweep-now --dry-run --source fake --no-bot  # smoke test, no network
python -m monitor.main --bot-only                # process Telegram commands, no sweep
python -m monitor.main --sweep-now --dry-run     # real fares, nothing sent
python -m monitor.main                           # a real tick (bot + sweep if due)
```

CLI flags: `--dry-run`, `--source`, `--sweep-now` (force sweep), `--no-bot`,
`--bot-only` (skip sweep), `--command "/excluir 3"` (run one bot command and exit —
also exposed as the `command` input on the `monitor-passagens` workflow_dispatch).

Tests: `pip install -r requirements-dev.txt && python -m pytest -q`
(pytest reads `pyproject.toml`, which puts `src/` on the path). `MONITOR_DB_PATH`
overrides the SQLite location — tests point it at a tmp file.

Routes: seeded from `config/routes.yaml` on first run, then managed via Telegram.
Dates must be in the future — Google Flights returns nothing for past dates.

## Conventions

- **Module structure:** `monitor.{config,models,storage,rules,notifier,telegram,bot,main}`
  plus `monitor.sources.*` for collectors. `telegram` = thin Bot API client;
  `bot` = command parsing/handlers (`handle_message` is pure, unit-tested);
  `explore` = on-demand destination sweep, its own `explorar` workflow (ADR-007).
- **Pluggable sources:** a new price source implements `PriceSource.search()` in
  `src/monitor/sources/`, is registered in `sources/__init__.py`, and changes
  nothing downstream. See ADR-002.
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

## Interview topics this project covers

| # | Topic | Where in the project |
|---|---|---|
| 1 | Technical Ownership | Every decision recorded in `docs/adr/` |
| 2 | Failure / adapting to change | ADR-001 — Amadeus Self-Service was decommissioned mid-build; the collector was re-pointed to `fast-flights` |
| 3 | Challenge the PM | ADR-002 rejects per-airline scraping; ADR-006 rejects an always-on host for an occasional-use feature |
| 4 | Architecture Document | `docs/adr/` + this file |
| 5 | Business Metrics | Alert precision (false positives), cost per run, route coverage — see ADR-003 |
| 6 | One Initiative + Metric | ADR-003 — historical baseline cuts noise alerts; metric = useful alerts / total alerts |
| 7 | AI-generated Code | Built with Claude Code; decisions reviewed through ADRs and PRs |
| 8 | Extensibility / Interface Design | ADR-002 — the `PriceSource` interface |
| 9 | Where AI fits (and where it doesn't) | ADR-005 — LLM-based promo classification evaluated and deferred |
| 10 | Test coverage of core logic | `tests/` — baseline/dedupe, alert rules, config, formatting, pipeline, route store, bot commands; CI on every push |
| 11 | Evolving under a new requirement | ADR-006 — interactive bot added by re-shaping the existing runtime, not rebuilding it; command handler is transport-agnostic |
| 12 | Where expensive work belongs | ADR-007 — the multi-minute explore sweep runs as its own on-demand workflow, isolated from the tick and the bot |
