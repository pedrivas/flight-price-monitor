# Flight Price Monitor

Personal tool that watches airfare for a set of routes and sends a **Telegram**
message when a fare hits a target price or drops sharply against its own history.

Built as a practical study for an AI Engineer interview — see [`CLAUDE.md`](CLAUDE.md)
for the interview-topic map and [`docs/adr/`](docs/adr/) for the decisions.

## Architecture

`python -m monitor.server` runs always-on in a container on a shared Oracle
Cloud VM, behind a Traefik edge, reached by a Telegram **webhook**
([ADR-008](docs/adr/ADR-008-vm-webhook-runtime.md), supersedes ADR-006):

```
Telegram ──HTTPS──▶ Traefik edge ──▶ POST /webhook/flight-tg ──▶ 200 na hora, enfileira
                                                                        │
                                              ┌─────────────────────────┴─────────────────────────┐
                                        fila rápida                                          fila lenta ◀ scheduler (1/min)
                                              │                                                     │
                                   worker rápido: handle_update                    worker lento: run_sweep / run_explore / backup
                                   (comandos comuns respondem na hora)             Collector (PriceSource) → Storage → Rules → Notifier
```

The collector is the only pluggable stage; downstream works on the normalized
`Offer` model ([ADR-002](docs/adr/ADR-002-pluggable-price-source-interface.md)).
All state — price history, the route list, the Telegram offset — lives in
`./data/history.db` on the VM (SQLite WAL; each worker holds its own connection).
It is no longer committed to git.

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
5. A Telegram message goes out: price, dates, carrier, the outbound itinerary
   (connection airports + layover time for each stop, total gate-to-gate
   duration), and a Google Flights link. Connection/duration detail is only
   available for the outbound leg — `fast-flights`' round-trip response doesn't
   include the return leg's segments — the message notes that when it applies.
6. **Hub option (opt-in per route):** the sweep also prices *two separate
   tickets*, origin⇄hub plus hub⇄destination, with 2 days of slack in the hub.
   Each hub is recorded under its own history key (`r7@LIS`), and a route sends
   at most one alert per sweep, for the cheapest option that passed. Hubs are
   discovered per destination region (`--hubs auto`) and kept only if they beat
   direct. See [ADR-009](docs/adr/ADR-009-hub-strategy-split-tickets.md).
7. **Open-jaw (`--volta-de`):** the route is priced as origin→dest on day d
   plus return_from→origin on d+N. The alert shows both tickets and a
   pre-filled multi-city Google Flights link. Use that link to check the
   single-ticket fare, which the free source can't price. See
   [ADR-010](docs/adr/ADR-010-open-jaw-as-two-one-ways.md).

## Bot commands

Send these to the bot (or the group) from a chat listed in `TELEGRAM_ALLOWED_CHAT_IDS`
(defaults to `TELEGRAM_CHAT_ID`). Answered in under a second by the webhook:

| Command | |
|---|---|
| `/monitorias` | list active monitors |
| `/criar GRU BEL 2026-09-04..2026-09-11 7-21 1700 15` | create (`ORIG DEST IDA_DE..IDA_ATE NIGHTS TARGET [DROP%] [--nonstop] [--pax N] [--hubs auto\|LIS,MAD] [--volta-de ATH]`; `NIGHTS = -` for one-way) |
| `/criar SAO IST 2027-04-01..2027-04-15 10-14 6000 --volta-de ATH` | open-jaw: arrive in IST, fly home from ATH (two linked one-way tickets, ADR-010); change with `/editar ID volta_de ATH\|-` |
| `/editar 3 alvo 1600` | edit a field: `nome alvo drop pax nonstop ida_de ida_ate noites hubs` (`hubs auto` rediscovers, `hubs -` turns off) |
| `/hubs SAO ATH 2027-04-01..2027-06-30 10-15 [LIS,MAD]` | one-off: direct vs. two separate tickets via each hub, per month; queued like `/explorar` |
| `/excluir 3` | remove (confirm with `/excluir 3 sim`) |
| `/pausar 3` · `/ativar 3` | toggle without deleting |
| `/explorar GRU 2026-10-01..2026-10-08 2026-10-15..2026-10-22 1800 [REC,SSA]` | which destinations fit a budget; queued on the slow worker, result arrives as a separate message a few minutes later |
| `/varrer` | force a price sweep now, outside the 6h gate |

For local dev without the webhook (`--bot-only`, polling), the same commands
work but `/explorar`/`/varrer` run inline and block until done — there's no
queue to hand them to outside the server process.

**One-off command without Telegram:**

```bash
PYTHONPATH=src python -m monitor.main --command "excluir 3"
```

prints the reply and, unless `--dry-run`, echoes it to the group too.

## Running locally

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env        # fill in the Telegram values

export PYTHONPATH=src
python -m monitor.main --sweep-now --dry-run --source fake --no-bot  # smoke test, no network
python -m monitor.main --bot-only                # handle Telegram commands only (polling)
python -m monitor.main --sweep-now --dry-run     # real fares, nothing sent
python -m monitor.main                           # one tick: bot poll + sweep if due
python -m monitor.main --backup-now              # force the OCI backup and exit

python -m monitor.server                         # the real always-on runtime (needs TELEGRAM_WEBHOOK_SECRET)
```

**Telegram:** create a bot with [@BotFather](https://t.me/BotFather), send it
`/start`, then run `python scripts/get_chat_id.py` to get `TELEGRAM_CHAT_ID`.

**Docker:**

```bash
docker compose config -q                                                     # validate syntax
docker compose run --rm app python -m monitor.main --sweep-now --dry-run --no-bot  # sweep from inside the image, no server
docker compose up -d                                                         # the real thing
```

## Tests

```bash
pip install -r requirements-dev.txt
python -m pytest -q
```

Covers date sampling, the SQLite baseline/dedupe logic, the route store, alert
rules, config parsing, Telegram formatting, bot command handling (including
`/explorar`/`/varrer` job dispatch), the webhook HTTP handler and its two
workers/scheduler (`test_server.py`, against a real ephemeral-port server),
the backup gate/upload (`test_backup.py`, `requests` mocked), and the tick
pipeline with the `fake` source. CI runs them on every push and PR
(`.github/workflows/ci.yml`).

## Configuring routes

First run only: `config/routes.yaml` seeds the `routes` table. Per-route fields:
`origin`/`dest` (IATA), `depart_range` `[start, end]` outbound window,
`return_after_days` `[min, max]` nights (omit for one-way), `adults`,
`target_price`, `drop_pct`, `nonstop`. Dates must be in the **future**.

After the first run, use the bot commands above — the DB is the source of truth
and the YAML is ignored.

## Deploying

Always-on on a shared Oracle Cloud Always Free VM behind a Traefik edge —
`docker-compose.yml` at the repo root, following the platform's contract in
the separate `vm-infra-oracle` repo (`docs/onboarding-a-project.md`). See
[ADR-008](docs/adr/ADR-008-vm-webhook-runtime.md) for the full design and the
cutover runbook.

`.env` needs (see `.env.example`): `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`,
`TELEGRAM_WEBHOOK_SECRET`, `WEBHOOK_URL` (used once by `scripts/set_webhook.py`),
and optionally `TELEGRAM_ALLOWED_CHAT_IDS`, `PRICE_SOURCE`, `OCI_BACKUP_PAR_URL`.

```bash
# on the VM, after `docker compose up -d` and a successful /healthz check:
python scripts/set_webhook.py set     # point Telegram at the webhook
python scripts/set_webhook.py info    # inspect (pending_update_count, last_error_message)
python scripts/set_webhook.py delete  # rollback to polling
```

GitHub Actions ran this as a `monitor-passagens` cron tick before ADR-008 —
see that ADR and ADR-006 for why it moved. Those workflow files are gone;
`ci.yml` is the only one left, running the test suite on every push/PR.

## Architecture Decision Records

- [ADR-001: Live Price Source Selection](docs/adr/ADR-001-live-price-source-selection.md)
- [ADR-002: Pluggable Price Source Interface](docs/adr/ADR-002-pluggable-price-source-interface.md)
- [ADR-003: Historical Baseline Alerting and Dedupe](docs/adr/ADR-003-historical-baseline-alerting.md)
- [ADR-004: GitHub Actions as Scheduler and History Store](docs/adr/ADR-004-github-actions-scheduler.md) *(superseded by ADR-006)*
- [ADR-005: LLM-Based Promo Classification — Deferred](docs/adr/ADR-005-llm-promo-classification-deferred.md)
- [ADR-006: Interactive Bot via Polling in the Existing Workflow](docs/adr/ADR-006-interactive-bot-and-polling-runtime.md)
- [ADR-007: Explore as a Separate On-Demand Workflow](docs/adr/ADR-007-explore-as-separate-dispatch-workflow.md) *(revisited by ADR-008 — `/explorar` is now a queued chat command)*
- [ADR-008: Always-On Runtime on the Oracle VM, via Webhook](docs/adr/ADR-008-vm-webhook-runtime.md)
- [ADR-009: Hub Strategy — Split Tickets as a Monitored Option](docs/adr/ADR-009-hub-strategy-split-tickets.md)
- [ADR-010: Open-Jaw Routes as Two Linked One-Way Tickets](docs/adr/ADR-010-open-jaw-as-two-one-ways.md)

## Explore (destination sweep)

The monitor watches fixed routes. Explore answers the other question — *given a
departure window, a return window and a budget, which destinations from one origin
fit?* It sweeps a curated list (~25 Brazil + South America destinations) and posts
the ranked result (under budget + a few near-misses) to the Telegram group.

It's slow (~100 fetches, 5–10 min). On the webhook runtime it's the `/explorar`
chat command (queued on the slow worker, doesn't block anything — see
[ADR-008](docs/adr/ADR-008-vm-webhook-runtime.md)); it can also be run directly:

```bash
PYTHONPATH=src python -m monitor.explore \
  --depart 2026-10-01..2026-10-08 --return 2026-10-15..2026-10-22 --max 1800 \
  [--origin GRU] [--destinations REC,SSA,BEL] [--dry-run]
```

The curated list lives in `DEFAULT_DESTS` in `src/monitor/explore.py`; override
per-run with `--destinations` / the command's last argument.

## Hub report (split tickets)

```bash
PYTHONPATH=src python -m monitor.hubs SAO ATH 2027-04-01..2027-06-30 10-15 [--hubs LIS,MAD] [--dry-run]
```

This is the same report as `/hubs`. It samples about one departure date per
week and prices direct against each hub. With no `--hubs`, it uses the
candidates for the destination's region (`HUB_CANDIDATES` in
`src/monitor/hubs.py`). Use `-` in place of nights for one-way.

## Adding a price source

Implement `PriceSource.search()` in `src/monitor/sources/`, register it in
`sources/__init__.py`, run with `--source <name>`. Nothing downstream changes.
Implementing `quote()` too, which prices one exact date pair, makes the source
usable for the hub strategy. Without it, hubs are skipped.

## Limitations

- `fastflights` depends on Google Flights' front-end; if it stops returning data,
  `fast-flights` has paid integrations (BrightData / SearchApi) as a fallback.
- ~4 dates sampled per window to avoid hammering the source; tune in
  `monitor/dates.py` (`sample_dates`). Round trips test one trip length (window midpoint).
- Round-trip stop count, connection airports and duration all reflect the
  outbound leg only — `fast-flights` doesn't expose the return leg's segments
  in the round-trip response.
- No direct booking link; alerts link to a Google Flights search.
- For WhatsApp instead of Telegram: swap `notifier.py` for a WhatsApp Cloud API
  client. Nothing else changes.
- The webhook depends on `vm-infra-oracle`'s Traefik edge being up; if it's
  down, inbound commands stop but the sweep/backup scheduler keeps running.
- `fast-flights`' `primp` (Rust) dependency needs an aarch64 wheel on the VM's
  A1 shape — validated in the cutover runbook, not assumed.

## License

MIT — see [LICENSE](LICENSE).
