# EdgeLedger

**A twelve-month, running, public system for pricing prediction markets — and an immutable,
timestamped record of every forecast it has ever made.**

Most trading track records are unverifiable: no one outside the author can tell whether a
backtest used information that didn't exist yet, or whether a "great year" survived because bad
trades were quietly dropped. EdgeLedger is built to make that kind of doubt impossible.

## What it does

EdgeLedger ingests live order books, trades, and resolutions from event-contract exchanges
(Kalshi, Polymarket — more venues later), and writes every forecast it generates to an
**append-only, hash-chained log** before the outcome is known. Nothing in that log can be
edited or deleted after the fact. Corrections are new rows, never overwrites.

Every forecast carries:
- the market's price *at the moment the forecast was made* — never joined in after the fact
- the exact feature data used, restricted to what existed at that timestamp
- a cryptographic link to the row before it, so the whole history can be verified end to end

The system is pregame-only and hold-to-resolution: it never trades in-play, and it runs
unattended — no action requires a human at a screen during a live event.

## Why it exists

This is a hiring portfolio for a quantitative researcher / trading-systems role on an
event-contract desk. The claim it exists to prove:

> I build the measurement and modelling layer that lets a desk know whether its edge is real —
> and I have twelve months of timestamped, out-of-sample forecasts to prove the layer works.

Twelve months of a deliberately naive baseline, progressively beaten (or not) by increasingly
serious models, reported quarterly against the market's own price as the baseline. If the edge
turns out to be zero after fees, that's a valid — and reported — result.

## The immutability guarantee

The `forecast_log` table is append-only by construction:

1. **No UPDATE, no DELETE, ever.** Enforced by the writer and asserted in tests.
2. **Market state is captured at forecast time, never joined afterwards.** Backfilling market
   price after the outcome is known is the single fastest way to fake an edge, and the first
   thing an experienced reviewer checks for.
3. **`feature_cutoff_ts_utc` is a contract.** Every feature used by a forecast must be derivable
   from data captured at or before that timestamp. This is the leakage firewall.
4. **Every row is hash-chained**: `row_hash = sha256(prev_row_hash + canonical_json(row))`. The
   daily head hash is published in this repo, turning "trust my track record" into a
   cryptographic proof that nothing was edited in hindsight.
5. **`seq` is gapless and monotonic.** A gap means a lost write, and is monitored as an
   incident.
6. **Every metric is reported against the market's own price as a baseline.** Raw accuracy
   numbers are not reported; only the delta against the market matters.

See `docs/methodology.md` for how forecasts are scored and `docs/data-model.md` for the full
schema.

## Status

Month 1 of 12: ingestion + the forecast log itself. See `docs/methodology.md` and the ADRs in
`docs/adr/` for the current state of the design. No forecasting model, sizing logic, or paper
execution exists yet — those are later milestones, deliberately.

## Non-goals

- Trading real capital. This is a research and measurement system, not a trading business.
- Live or in-game trading of any kind.
- There is no order-placement code anywhere in this repository.

## Stack

Python 3.12, `uv`, `httpx`, `pydantic`, `polars`, `deltalake`, `duckdb`, Airflow (local),
`pytest`, `ruff`. No Spark — the data volume doesn't justify it.

## License

TBD.
