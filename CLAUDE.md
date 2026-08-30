# Flight Price Monitor — CLAUDE.md

## Project overview

Personal tool that watches airfare for a set of routes and sends a Telegram
message when a fare hits a target price or drops sharply against its own history.

This project is a practical study for an AI Engineer interview. Each architectural
decision maps to a specific interview topic (see `docs/adr/` and the table below).
It deliberately ships **without** an LLM in the hot path — ADR-005 documents where
one would fit and why it was deferred.

## Architecture

Single Python process, four stages, run on a schedule:

```
Scheduler (GitHub Actions / cron)
   └─ Collector    — a PriceSource implementation queries live fares
        └─ Storage — SQLite: append price history, compute 30-day baseline
             └─ Rules — target price OR drop vs. baseline, with dedupe
                  └─ Notifier — Telegram message + Google Flights link
```

The collector is the only pluggable part. Everything downstream works on the
normalized `Offer` model and never knows which source produced it.

## Stack

- Python 3.10+ (standard library + `requests`, `PyYAML`, `python-dotenv`)
- `fast-flights` — live Google Flights data (default source)
- SQLite — price history and alert dedupe (no server)
- Telegram Bot API — delivery
- GitHub Actions — scheduler and history persistence (see ADR-004)

## Running locally

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env        # fill in the Telegram values

export PYTHONPATH=src
python -m monitor.main --dry-run --source fake   # pipeline smoke test, no network
python -m monitor.main --dry-run                 # real fares, nothing sent
python -m monitor.main                           # real run
```

Routes are configured in `config/routes.yaml`. Dates must be in the future —
Google Flights returns nothing for past dates.

## Conventions

- **Module structure:** `monitor.{config,models,storage,rules,notifier,main}` plus
  `monitor.sources.*` for collectors.
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
| `TELEGRAM_BOT_TOKEN` | `notifier` | Bot token from @BotFather |
| `TELEGRAM_CHAT_ID` | `notifier` | Destination chat (see `scripts/get_chat_id.py`) |
| `TRAVELPAYOUTS_TOKEN` | `travelpayouts` source | Affiliate API token (optional) |
| `TRAVELPAYOUTS_MARKER` | `travelpayouts` source | Affiliate marker / partner ID (optional) |

## Interview topics this project covers

| # | Topic | Where in the project |
|---|---|---|
| 1 | Technical Ownership | Every decision recorded in `docs/adr/` |
| 2 | Failure / adapting to change | ADR-001 — Amadeus Self-Service was decommissioned mid-build; the collector was re-pointed to `fast-flights` |
| 3 | Challenge the PM | ADR-002 rejects per-airline scraping; ADR-004 rejects an always-on VPS |
| 4 | Architecture Document | `docs/adr/` + this file |
| 5 | Business Metrics | Alert precision (false positives), cost per run, route coverage — see ADR-003 |
| 6 | One Initiative + Metric | ADR-003 — historical baseline cuts noise alerts; metric = useful alerts / total alerts |
| 7 | AI-generated Code | Built with Claude Code; decisions reviewed through ADRs and PRs |
| 8 | Extensibility / Interface Design | ADR-002 — the `PriceSource` interface |
| 9 | Where AI fits (and where it doesn't) | ADR-005 — LLM-based promo classification evaluated and deferred |
