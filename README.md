# Flight Price Monitor

Personal tool that watches airfare for a set of routes and sends a **Telegram**
message when a fare hits a target price or drops sharply against its own history.

Built as a practical study for an AI Engineer interview — see [`CLAUDE.md`](CLAUDE.md)
for the interview-topic map and [`docs/adr/`](docs/adr/) for the decisions.

## Architecture

One GitHub Actions workflow runs a "tick" every ~20 minutes ([ADR-006](docs/adr/ADR-006-interactive-bot-and-polling-runtime.md)):

```
tick
 ├─ bot        — Telegram getUpdates → /monitorias /criar /editar /excluir
 └─ if ≥6h since last sweep:
      Collector (PriceSource) → Storage (SQLite) → Rules → Notifier (Telegram)
```

The collector is the only pluggable stage; downstream works on the normalized
`Offer` model ([ADR-002](docs/adr/ADR-002-pluggable-price-source-interface.md)).
All state — price history, the route list, and the bot's read offset — lives in
`data/history.db`, which the workflow commits back after every tick.

## Price sources

| `--source` | Data | Signup | Notes |
|---|---|---|---|
| `fastflights` (default) | Google Flights, live, in BRL | No | `fast-flights` lib. Unofficial; can break on Google front-end changes. Personal use. |
| `travelpayouts` | Aviasales real-time metasearch | Yes (free affiliate) | **Untested draft** in `sources/travelpayouts.py` — needs `marker` + `token`. |
| `fake` | Synthetic | No | Pipeline testing only. |

Amadeus Self-Service was decommissioned on 2026-07-17 — see
[ADR-001](docs/adr/ADR-001-live-price-source-selection.md).

## How it works

1. Routes are seeded once from `config/routes.yaml` into the `routes` table; from
   then on you manage them from Telegram.
2. When a sweep is due, the collector fetches fares and stores the cheapest,
   keyed by the route row id (so editing a route keeps its history).
3. It alerts when `price <= target_price` **or** `price <= median_30d * (1 - drop_pct%)`.
4. Dedupe: the same promo is not re-sent (fares within 2% over the last 7 days).
5. A Telegram message goes out with a Google Flights link.

## Bot commands

Send these to the bot (or the group) from a chat listed in `TELEGRAM_ALLOWED_CHAT_IDS`
(defaults to `TELEGRAM_CHAT_ID`):

| Command | |
|---|---|
| `/monitorias` | list active monitors |
| `/criar GRU BEL 2026-09-04..2026-09-11 7-21 1700 15` | create (`ORIG DEST IDA_DE..IDA_ATE NIGHTS TARGET [DROP%] [--nonstop] [--pax N]`; `NIGHTS = -` for one-way) |
| `/editar 3 alvo 1600` | edit a field: `nome alvo drop pax nonstop ida_de ida_ate noites` |
| `/excluir 3` | remove (confirm with `/excluir 3 sim`) |
| `/pausar 3` · `/ativar 3` | toggle without deleting |

Commands are processed on the next tick (typically 0–20 min; GitHub cron is best-effort — see ADR-006).

**Faster path**, no Telegram round-trip: run a single command on demand via
`workflow_dispatch` (~40 s):

```bash
gh workflow run monitor-passagens -f command="/excluir 3"
```

or the GitHub UI/mobile app: *Actions → monitor-passagens → Run workflow*, fill the
`command` field. The reply is printed in the run log and echoed to the group.

## Running locally

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env        # fill in the Telegram values

export PYTHONPATH=src
python -m monitor.main --sweep-now --dry-run --source fake --no-bot  # smoke test, no network
python -m monitor.main --bot-only                # handle Telegram commands only
python -m monitor.main --sweep-now --dry-run     # real fares, nothing sent
python -m monitor.main                           # a real tick
```

**Telegram:** create a bot with [@BotFather](https://t.me/BotFather), send it
`/start`, then run `python scripts/get_chat_id.py` to get `TELEGRAM_CHAT_ID`.

## Tests

```bash
pip install -r requirements-dev.txt
python -m pytest -q
```

Covers date sampling, the SQLite baseline/dedupe logic, the route store, alert
rules, config parsing, Telegram formatting, bot command handling, and the tick
pipeline with the `fake` source. CI runs them on every push and PR
(`.github/workflows/ci.yml`).

## Configuring routes

First run only: `config/routes.yaml` seeds the `routes` table. Per-route fields:
`origin`/`dest` (IATA), `depart_range` `[start, end]` outbound window,
`return_after_days` `[min, max]` nights (omit for one-way), `adults`,
`target_price`, `drop_pct`, `nonstop`. Dates must be in the **future**.

After the first run, use the bot commands above — the DB is the source of truth
and the YAML is ignored.

## Scheduling

**GitHub Actions** (free on public repos): `.github/workflows/monitor.yml` runs
the tick roughly every 20 min and commits `data/history.db` back — see
[ADR-006](docs/adr/ADR-006-interactive-bot-and-polling-runtime.md). Configure
under *Settings → Secrets and variables → Actions*:

- Secrets: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` (and `TRAVELPAYOUTS_*` if used)
- Variables (optional): `PRICE_SOURCE` (default `fastflights`),
  `TELEGRAM_ALLOWED_CHAT_IDS` (default `TELEGRAM_CHAT_ID`)

## Architecture Decision Records

- [ADR-001: Live Price Source Selection](docs/adr/ADR-001-live-price-source-selection.md)
- [ADR-002: Pluggable Price Source Interface](docs/adr/ADR-002-pluggable-price-source-interface.md)
- [ADR-003: Historical Baseline Alerting and Dedupe](docs/adr/ADR-003-historical-baseline-alerting.md)
- [ADR-004: GitHub Actions as Scheduler and History Store](docs/adr/ADR-004-github-actions-scheduler.md) *(superseded by ADR-006)*
- [ADR-005: LLM-Based Promo Classification — Deferred](docs/adr/ADR-005-llm-promo-classification-deferred.md)
- [ADR-006: Interactive Bot via Polling in the Existing Workflow](docs/adr/ADR-006-interactive-bot-and-polling-runtime.md)

## One-off destination sweep

The monitor watches fixed routes. To scan many destinations from one origin for a
round trip under a budget (e.g. "anywhere from São Paulo under R$ 1800"):

```bash
PYTHONPATH=src python scripts/explore.py 1800   # budget is optional, default 1800
```

Edit the `DESTS` / `DEPARTS` / `RETURNS` lists at the top of the script. It is a
throwaway helper, not wired into the pipeline.

## Adding a price source

Implement `PriceSource.search()` in `src/monitor/sources/`, register it in
`sources/__init__.py`, run with `--source <name>`. Nothing downstream changes.

## Limitations

- `fastflights` depends on Google Flights' front-end; if it stops returning data,
  `fast-flights` has paid integrations (BrightData / SearchApi) as a fallback.
- ~4 dates sampled per window to avoid hammering the source; tune in
  `monitor/dates.py` (`sample_dates`). Round trips test one trip length (window midpoint).
- Round-trip stop count reflects the outbound leg only.
- No direct booking link; alerts link to a Google Flights search.
- For WhatsApp instead of Telegram: swap `notifier.py` for a WhatsApp Cloud API
  client. Nothing else changes.

## License

MIT — see [LICENSE](LICENSE).
