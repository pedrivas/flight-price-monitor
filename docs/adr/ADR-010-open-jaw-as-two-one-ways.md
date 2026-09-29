# ADR-010: Open-Jaw Routes as Two Linked One-Way Tickets

**Status:** Accepted
**Date:** 2026-09-29

## Context

The user wants to fly São Paulo → Istanbul and come back Athens → São Paulo.
The Istanbul → Athens stretch is on their own. Airlines sell this as a single
**multi-city (open-jaw)** ticket. Every route in the monitor so far was a
round trip or a one-way from `origin` to `dest`.

The natural implementation would price that single ticket. A live probe
(2026-09-29) showed the free source can't do it:

- `fast-flights`' `trip="multi-city"` returns a page with **no flights at
  all**, for every date pair tried. Google loads multi-city results
  client-side after the first leg is picked. The library's parser also
  crashes on it (`payload[7][1][1]`).
- A `round-trip` query with a mismatched return leg (`ATH→GRU`) is not an
  open-jaw. Google silently answers with the plain `GRU⇄IST` round trip, with
  identical results in both blocks.
- The paid SearchApi integration in `fast-flights` does support
  `multi_city`. It is paid.

## Decision

An open-jaw route is **two one-way tickets with linked dates**, priced through
the same `PriceSource.quote()` the hub strategy uses (ADR-009):

```
out   origin → dest          on d
back  return_from → origin   on d + N    (N = midpoint of the nights range, as elsewhere)
```

- **Model / storage:** `RouteQuery.return_from` backs a new `routes.return_from`
  column, added by the startup migration. `None` means a normal route.
- **History key:** the route's own `r<id>`. The whole route is open-jaw, so
  there is no second option to keep apart. This differs from hubs, which use
  `r<id>@HUB`.
- **Sweep:** `search_openjaw()` replaces `source.search()` for that route.
  That is 2 fetches per sampled date, sharing the per-sweep leg cache.
- **Mutually exclusive with hubs.** The bot refuses `--volta-de` with
  `--hubs`, and `/editar` refuses the reverse. The sweep ignores hubs on an
  open-jaw route as a backstop. Combining them multiplies fetches and makes
  the alert hard to read.
- **Nights are required.** A one-way open-jaw is just a one-way to `dest`.
- **Alert:** reuses the two-ticket format, titled "chega em X, volta de Y". It
  carries a link per leg and a **pre-filled multi-city Google Flights link**,
  plus the note that the single ticket may be cheaper. The text link (`?q=`)
  does not understand multi-city, so that link uses the encoded `tfs`
  parameter, built with `fast_flights.create_query(trip="multi-city")`. It
  opens the correct "Várias cidades" form.

## Consequences

**Positive**
- Open-jaw trips can be monitored today, with the free source and no new
  dependency.
- Small surface. The date logic lives in `openjaw.py` (~40 lines). Leg
  pricing, the cache, the alert format and the migration are reused from
  ADR-009.

**Negative / accepted**
- **The alert price is an upper bound.** Two one-ways are usually somewhat
  dearer than the single open-jaw fare. Treat the alert as "this trip is
  cheap now" and check the final price with the multi-city link. How big the
  gap is must be measured by hand against Google Flights. It is not known yet.
- The positioning leg (Istanbul → Athens) is not priced. Its date is the
  traveller's choice.

## Rejected alternatives

- **Scrape the multi-city flow.** It needs a real browser to pick the first
  leg and trigger the client-side load. That is heavy on a 384 MB container
  and fragile.
- **SearchApi `multi_city`.** It gives the correct price, but it is a paid
  API. It is the upgrade path if the one-way gap turns out to be large.
- **Two independent one-way monitors.** Already possible today. There is no
  combined total, and the return window doesn't move with the outbound.
