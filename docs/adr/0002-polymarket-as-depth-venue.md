# ADR-0002: Polymarket as the Orderbook Depth Venue

## Status

Accepted — 2026-08-03

## Context

The original month-1 design treated Kalshi and Polymarket symmetrically: ingest markets, trades,
resolutions and **orderbook depth** from both, and use depth for spread-aware metrics and
closing-line value.

Kalshi's depth endpoint (`GET /markets/{ticker}/orderbook`) is the only Kalshi endpoint that
requires authentication — an access key plus RSA-PSS per-request signing. Obtaining that key pair
requires a verified Kalshi account.

Two facts, both verified on 2026-08-03, make that unobtainable here:

1. **`kalshi.com` is blocked from Portugal** pursuant to a judicial/administrative order (SRIJ,
   the Portuguese gambling regulator, blocking unlicensed betting operators). The block is a DNS
   hijack: `kalshi.com` resolves to `213.30.114.136`, a Portuguese ISP block page, not to
   Kalshi's infrastructure. Signup, identity verification, and the API-key management page are
   all behind that block.
2. **Kalshi requires US residency and KYC** to open an account, which the operator of this
   project does not have.

Circumventing the block to create an account would mean misrepresenting location and residency to
the venue — a terms-of-service violation in a regulated context. It is not an option this project
will take.

Notably, **Kalshi's API hosts are *not* blocked.** `external-api.kalshi.com` and
`api.elections.kalshi.com` resolve to genuine AWS infrastructure and return HTTP 200 with live
market data. Only the consumer website is hijacked. So Kalshi remains a usable data source for
everything that does not require a signed request.

## Decision

**Polymarket is the orderbook depth venue. Kalshi contributes markets, trades, and resolutions
only.**

- Depth comes from Polymarket's CLOB (`GET /book`), which is unauthenticated and returns full
  depth — measured at 8–16 bid levels and 19–45 ask levels per token on live markets, materially
  deeper than a top-of-book snapshot.
- Kalshi ingestion continues unchanged against its unauthenticated endpoints: `/markets`,
  `/markets/{ticker}`, `/markets/trades`, `/events`, `/series`, `/historical/markets`.
- `KalshiClient.get_orderbook` raises `NotImplementedError` and documents why. It is not dead
  code to be deleted: if the operator's eligibility ever changes, the endpoint and its signing
  requirement are already mapped.
- Kalshi's rate limit stays `null` in `venues.yaml` (still unconfirmed against live docs), so the
  client falls back to a conservative 30 req/min.

## Consequences

**Easier:** no credential management, no key rotation, no RSA-PSS signing implementation, and no
secret material anywhere in the pipeline for month 1. Depth ingestion has no auth failure mode.

**Harder:** depth-derived metrics — effective spread, depth-weighted mid, slippage estimates,
book-imbalance features — exist for Polymarket markets only. Any cross-venue comparison of those
specific metrics is unavailable, and **this asymmetry must be stated wherever such a metric is
reported.** A depth metric quoted without naming its venue would misrepresent the coverage.

Metrics that do **not** depend on depth — Brier, log loss, calibration, and closing-line value
computed from mids — remain fully cross-venue, because Kalshi's unauthenticated endpoints supply
prices, trades, and resolutions. The headline scoring in `docs/methodology.md` is therefore
unaffected.

**Forecloses:** nothing permanently. This is a constraint of circumstance, not of design. If
Kalshi depth becomes obtainable, it is additive: a new client method, no schema change, and no
rewrite of anything that already exists.

## Related

- `docs/methodology.md` — "Venue coverage" records the asymmetry for anyone reading the results.
- `src/edgeledger/clients/polymarket.py` — depth implementation.
- `src/edgeledger/clients/kalshi.py` — `get_orderbook` documents the blocker at the call site.
