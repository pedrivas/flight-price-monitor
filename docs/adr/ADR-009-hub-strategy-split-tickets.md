# ADR-009: Hub Strategy — Split Tickets as a Monitored Option

**Status:** Accepted
**Date:** 2026-09-28

## Context

A manual analysis for São Paulo → Athens (April–June 2027) showed that buying
**two separate tickets** — São Paulo → a European hub, then hub → Athens — was
up to ~20% cheaper than the cheapest single ticket Google Flights returned. It
only worked through *some* hubs: Madrid and Lisbon won, while Paris, Istanbul,
Amsterdam and Frankfurt never did. The monitor only knew about single tickets,
so it could never alert on this.

The obvious shortcut is a fixed list, "always also try LIS and MAD". But the
user also monitors Cairo, Hanoi, Manila, Bangkok, Morocco, and so on. For those,
Lisbon is meaningless and the winning hub, if any, is somewhere else.

## Decision

**1. Two round-trip tickets, the inner one nested in the outer one.**

```
outer  origin ⇄ hub    out d        back d+N
inner  hub ⇄ dest      out d+2      back d+N-2
```

Two days of slack sit on each side of the inner ticket. The overnight
Brazil→Europe flight lands the next day. With separate tickets, nobody rebooks
you if the first flight is late. Trips shorter than 5 nights leave no room for
the inner ticket, so the hub is skipped and the skip is logged. One-way routes
use `origin→hub` on day d and `hub→dest` on day d+2.

**2. Hubs are discovered per route, not fixed.** `hubs.py` keeps candidate
lists per destination *region* (from `airports.py`), tuned for departures from
Brazil. There is also a global fallback for unknown airports.
`/criar … --hubs auto` and `/editar ID hubs auto` queue a `discover_hubs` job
on the slow worker. The job prices direct and every candidate over 3 sampled
dates, then keeps up to 2 hubs that **beat direct**. It may keep none; that is a
valid answer and it is reported as such. Explicit lists (`--hubs LIS,MAD`) skip
discovery.

**3. Each option has its own history key.** A hub option is recorded under
`r7@LIS`, next to the direct `r7`. The median baseline and the dedupe
(ADR-003) are computed per option. A cheap hub price never makes the direct
fare look like a "drop", and the other way around. The direct key is
unchanged, so existing history survives the rollout.

**4. At most one alert per route per sweep.** Direct and each hub are evaluated
independently. Among the options that pass, only the cheapest is sent. A hub
alert also carries "today's direct price" for comparison, one block and one
Google Flights link per ticket, and an explicit warning about separate tickets
and baggage.

**5. `quote()` on `PriceSource`.** The hub logic needs to control each leg's
dates exactly, and `search(route)` samples dates by itself. `quote(origin,
dest, depart, return_date)` is the lower-level call, and
`FastFlightsSource.search` is now a loop over it. It is optional:
`Travelpayouts` does not implement it. There the sweep logs once and keeps
monitoring direct only. ADR-002's contract, "`search()` is all a source must
provide", still holds.

**6. `/hubs` for one-off analysis.** The same comparison, month by month, as a
queued chat command (and `python -m monitor.hubs`). It covers the "should I
even bother" question before creating a monitor.

## What the live test showed

The first live run of `/hubs SAO ATH` for April 2027 repeated the one-way
finding: direct R$ 3.831, via Madrid R$ 3.205 (−626). As **two round trips**
(12 nights), direct won: R$ 5.211 against R$ 5.541 via Madrid. The saving
depends on direction, dates and the route. That is the reason discovery
compares against direct instead of assuming a hub helps.

## Consequences

**Positive**
- Surfaces fares the single-ticket search structurally cannot find.
- Opt-in and per route. Routes without hubs cost exactly what they did before.
- A shared per-sweep cache means a leg used by two routes (e.g. `LIS⇄ATH`) is
  fetched once.

**Negative / accepted**
- Cost: 2 fetches per hub per sampled date. That is ~16 extra fetches for a
  route with 2 hubs, against a baseline sweep of ~32. Discovery is heavier,
  `3 × (1 + 2×candidates)`, around 50 fetches for Europe. It runs only on
  request.
- Missed-connection risk and double baggage fees are the traveller's to
  accept. The alert states both but does not price them in.
- Discovered hubs go stale as fares move. Re-running discovery is manual for
  now (`/editar ID hubs auto`).

## Rejected alternatives

- **Fixed global hub list (LIS, MAD).** Right for Athens, wrong for most other
  destinations the user monitors.
- **Four one-way tickets.** The most flexible option, but it doubles fetches
  again. Round-trip fares on the long-haul leg are also often cheaper than two
  one-ways.
- **Different hub on the way back.** Combinatorial fetch growth for a marginal
  gain. Left as a future extension.
- **Hubs in `/explorar`.** Multiplies an already ~100-fetch sweep by the
  number of candidates.
