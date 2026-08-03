# ADR-0001: Append-Only, Hash-Chained Forecast Log

## Status

Accepted

## Context

EdgeLedger's entire hiring case rests on a track record being verifiably real: that forecasts
were made before outcomes were known, using only data that existed at that moment, and were
never edited in hindsight. A conventional mutable table (even one with an `updated_at` column)
cannot prove any of that to a skeptical outside reviewer — it can only assert it.

## Decision

`forecast_log` is append-only by construction:

1. No UPDATE, no DELETE, ever. Enforced in the writer (`forecast/log.py`) and asserted in tests
   (`tests/test_hash_chain.py`). Corrections are new rows carrying `supersedes_forecast_id`.
2. Market state (bid/ask/mid/spread/depth/volume) is captured and embedded in the row at
   forecast-write time, never joined in afterwards.
3. `feature_cutoff_ts_utc` is a contract: every feature in `feature_vector` must be derivable
   only from data captured at or before that timestamp (`tests/test_point_in_time.py`).
4. Every row is hash-chained: `row_hash = sha256(prev_row_hash + canonical_json(row))`. The
   daily head hash is published to this repo.
5. `seq` is gapless and monotonic; a gap means a lost write and is treated as an incident.
6. Resolutions live in a separate table (`resolutions`), joined only at query time via
   `forecast_scored` — the forecast row itself never learns the outcome.

## Consequences

**Easier:** an outside reviewer can independently verify the entire history by recomputing the
hash chain from the genesis row — no need to trust the operator's word.

**Harder:** any schema change to `forecast_log` is effectively permanent for rows already
written; new fields must be nullable-additive, and any real correction requires a new row plus a
`supersedes_forecast_id` link rather than a quick edit.

**Forecloses:** any code path that updates or deletes a forecast row after the fact. There is no
such path anywhere in this repository, by design.
