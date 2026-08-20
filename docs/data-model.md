# Data Model

## Bronze layer (raw, verbatim)

Four tables. Every row carries `capture_ts_utc` (when *we* fetched it — distinct from any venue
timestamp, per invariant 8) and a verbatim `payload` JSON column. Never transformed on write.

### `bronze.venue_market_snapshot`

| Column | Type | Notes |
|---|---|---|
| `capture_ts_utc` | TIMESTAMP | when WE fetched |
| `run_id` | STRING | |
| `venue` | STRING | `kalshi` \| `polymarket` |
| `venue_market_id` | STRING | ticker \| conditionId |
| `payload` | STRING | full JSON, verbatim |
| `ingest_date` | DATE | partition key |

### `bronze.venue_orderbook_snapshot`

| Column | Type | Notes |
|---|---|---|
| `capture_ts_utc` | TIMESTAMP | |
| `venue` | STRING | |
| `venue_market_id` | STRING | |
| `outcome_side` | STRING | `yes` \| `no` |
| `bids` | STRING | JSON `[[price, size], ...]` |
| `asks` | STRING | |
| `payload` | STRING | |
| `ingest_date` | DATE | |

### `bronze.venue_trade`

| Column | Type | Notes |
|---|---|---|
| `capture_ts_utc` | TIMESTAMP | |
| `venue` | STRING | |
| `venue_market_id` | STRING | |
| `venue_trade_id` | STRING | dedupe key |
| `trade_ts_utc` | TIMESTAMP | venue's own timestamp |
| `price` | DECIMAL(6,4) | |
| `size` | DECIMAL(18,4) | |
| `payload` | STRING | |
| `ingest_date` | DATE | |

### `bronze.resolution`

| Column | Type | Notes |
|---|---|---|
| `capture_ts_utc` | TIMESTAMP | |
| `venue` | STRING | |
| `venue_market_id` | STRING | |
| `resolved_outcome` | STRING | `yes` \| `no` \| `invalid` |
| `resolution_ts_utc` | TIMESTAMP | |
| `payload` | STRING | |

## The forecast log — `forecast_log`

The credibility artifact. Full field list, grouped by purpose (mirrors
`src/edgeledger/forecast/schema.py::ForecastLogRow`, the single source of truth):

- **Identity:** `forecast_id` (UUIDv7), `seq` (monotonic, gapless), `forecast_ts_utc`
- **Provenance:** `model_name`, `model_version` (semver), `code_git_sha`, `run_id`
- **Market identity:** `venue`, `venue_market_id`, `canonical_market_id` (nullable, cross-venue
  link), `market_question`, `category` (nullable), `outcome_side` (always `yes`)
- **The prediction:** `p_hat`, `p_hat_lo`/`p_hat_hi` (nullable 90% interval)
- **Market state at forecast time** (never backfilled): `mkt_yes_bid`, `mkt_yes_ask`,
  `mkt_yes_mid`, `mkt_spread`, `mkt_depth_1pct`, `mkt_volume_cum`, `orderbook_ref`
- **Point-in-time contract:** `feature_cutoff_ts_utc`, `feature_vector` (JSON),
  `feature_set_version`
- **Derived at write time:** `edge` (`p_hat - mkt_yes_mid`), `horizon_seconds`
- **Intent, not execution:** `intended_stake_units`, `sizing_rule` — no order-placement path
  consumes these anywhere in this repo
- **Tamper evidence:** `row_hash`, `prev_row_hash`
- **Supersession:** `supersedes_forecast_id` (nullable) — corrections are new rows, never edits

Partitioned by `forecast_date`.

## Scoring view — `forecast_scored`

Recomputable, joins `forecast_log` against `resolutions` and `closing_prices` at query time.
DDL: `src/edgeledger/scoring/views.sql`. The inputs are built by
`src/edgeledger/scoring/score.py` (`uv run python3 -m edgeledger.scoring.score`), which loads
the log and bronze into DuckDB in memory and writes nothing back. `closing_prices` is derived —
the last snapshot mid at or before resolution, never a post-settlement price — and carries
`close_lag_seconds` so staleness is measurable. See `docs/methodology.md` for what each metric
means and how the inputs are built.

## Hash chain

`row_hash = sha256(prev_row_hash + canonical_json(row_without_hashes))`. The genesis row's
`prev_row_hash` is a fixed constant (`"genesis"`), chosen in `forecast/log.py`. The daily head
hash is published to this repo so the full chain is independently verifiable.
