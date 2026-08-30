# Flight Price Monitor

Personal tool that watches airfare for a set of routes and sends a **Telegram**
message when a fare hits a target price or drops sharply against its own history.

Built as a practical study for an AI Engineer interview — see [`CLAUDE.md`](CLAUDE.md)
for the interview-topic map and [`docs/adr/`](docs/adr/) for the decisions.

## Architecture

```
Scheduler (GitHub Actions / cron)
   └─ Collector    — a PriceSource queries live fares
        └─ Storage — SQLite: price history + 30-day baseline
             └─ Rules — target price OR drop vs. baseline, with dedupe
                  └─ Notifier — Telegram message + Google Flights link
```

The collector is the only pluggable stage. Everything downstream works on the
normalized `Offer` model (see [ADR-002](docs/adr/ADR-002-pluggable-price-source-interface.md)).

## Price sources

| `--source` | Data | Signup | Notes |
|---|---|---|---|
| `fastflights` (default) | Google Flights, live, in BRL | No | `fast-flights` lib. Unofficial; can break on Google front-end changes. Personal use. |
| `travelpayouts` | Aviasales real-time metasearch | Yes (free affiliate) | **Untested draft** in `sources/travelpayouts.py` — needs `marker` + `token`. |
| `fake` | Synthetic | No | Pipeline testing only. |

Amadeus Self-Service was decommissioned on 2026-07-17 — see
[ADR-001](docs/adr/ADR-001-live-price-source-selection.md).

## How it works

1. `config/routes.yaml` lists the monitored routes.
2. Each run, the collector fetches fares and stores the cheapest in `data/history.db`.
3. `rules.py` alerts when `price <= target_price` **or**
   `price <= median_30d * (1 - drop_pct%)`.
4. Dedupe: the same promo is not re-sent (fares within 2% over the last 7 days).
5. `notifier.py` sends a Telegram message with a Google Flights link.

## Running locally

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env        # fill in the Telegram values

export PYTHONPATH=src
python -m monitor.main --dry-run --source fake   # smoke test, no network
python -m monitor.main --dry-run                 # real fares, nothing sent
python -m monitor.main                           # real run
```

**Telegram:** create a bot with [@BotFather](https://t.me/BotFather), send it
`/start`, then run `python scripts/get_chat_id.py` to get `TELEGRAM_CHAT_ID`.

## Tests

```bash
pip install -r requirements-dev.txt
python -m pytest -q
```

Covers date sampling, the SQLite baseline/dedupe logic, alert rules, config
parsing and validation, Telegram message formatting (HTML escaping), and the
`run()` pipeline end to end with the `fake` source. CI runs them on every push
and PR (`.github/workflows/ci.yml`).

## Configuring routes

Edit `config/routes.yaml`. Per-route fields:

| Field | Meaning |
|---|---|
| `origin` / `dest` | IATA code (airport or city) |
| `depart_range` | `[start, end]` outbound window; ~4 dates are sampled inside it |
| `return_after_days` | `[min, max]` trip length in nights (omit for one-way) |
| `adults` | passenger count (alert price is the **total**, not per person) |
| `target_price` | alert if price ≤ this value (in `currency`) |
| `drop_pct` | also alert if price falls ≥ this % vs. the 30-day median |
| `nonstop` | `true` = direct flights only |

Dates must be in the **future** — Google Flights returns nothing for past dates.

## Scheduling

**GitHub Actions** (free): `.github/workflows/monitor.yml` runs every 6h and
commits `data/history.db` back to keep the baseline — see
[ADR-004](docs/adr/ADR-004-github-actions-scheduler.md). Configure under
*Settings → Secrets and variables → Actions*:

- Secrets: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` (and `TRAVELPAYOUTS_*` if used)
- Variable (optional): `PRICE_SOURCE` (default `fastflights`)

**Local cron:**

```cron
17 */6 * * * cd /path/flight-price-monitor && PYTHONPATH=src .venv/bin/python -m monitor.main
```

## Architecture Decision Records

- [ADR-001: Live Price Source Selection](docs/adr/ADR-001-live-price-source-selection.md)
- [ADR-002: Pluggable Price Source Interface](docs/adr/ADR-002-pluggable-price-source-interface.md)
- [ADR-003: Historical Baseline Alerting and Dedupe](docs/adr/ADR-003-historical-baseline-alerting.md)
- [ADR-004: GitHub Actions as Scheduler and History Store](docs/adr/ADR-004-github-actions-scheduler.md)
- [ADR-005: LLM-Based Promo Classification — Deferred](docs/adr/ADR-005-llm-promo-classification-deferred.md)

## Adding a price source

Implement `PriceSource.search()` in `src/monitor/sources/`, register it in
`sources/__init__.py`, run with `--source <name>`. Nothing downstream changes.

## Limitations

- `fastflights` depends on Google Flights' front-end; if it stops returning data,
  `fast-flights` has paid integrations (BrightData / SearchApi) as a fallback.
- ~4 dates sampled per window to avoid hammering the source; tune in
  `sources/fastflights.py` (`_sample_dates`).
- Round-trip stop count reflects the outbound leg only.
- No direct booking link; alerts link to a Google Flights search.
- For WhatsApp instead of Telegram: swap `notifier.py` for a WhatsApp Cloud API
  client. Nothing else changes.

## License

MIT — see [LICENSE](LICENSE).
