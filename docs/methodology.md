# Methodology

How forecasts are logged and scored. Update this file whenever scoring logic changes
(CLAUDE.md "before you commit" checklist).

## What gets forecast

Every tracked open market, on both venues, gets a `p_hat` — the probability of the "yes"
outcome — from whichever model is currently in production for that market category. Month 1
runs exactly two deliberately naive models (see below); real models arrive from month 5.

## How a forecast is written

1. A model computes `p_hat` from a `feature_vector` built entirely from bronze data captured at
   or before `feature_cutoff_ts_utc`.
2. The market's own state (bid/ask/mid/spread/depth/volume) is read **at that same moment** and
   embedded in the row. It is never joined in afterwards — see invariant 2.
3. The row is hash-chained to the previous row and appended. It is never edited again.

## How the point-in-time claim is enforced

Step 1 above is a claim about evidence, and a claim about evidence is worth what its test is
worth. `feature_cutoff_ts_utc` is enforced in two independent places, and tested in three.

**In the code.** The forecast runner filters twice: once when selecting the newest snapshot per
market, and again inside `build_feature_vector`, which is the single point where bronze rows are
admitted to a forecast. The filter is `capture_ts_utc <= feature_cutoff_ts_utc` and nothing
else — no venue timestamp, no tolerance window. Any tolerance is a leak, and a leak is
indistinguishable from a model that appears to work.

**In the tests** (`tests/test_point_in_time.py`), three checks at different altitudes:

| Check | What it would catch |
|---|---|
| `test_feature_builder_excludes_data_after_cutoff` | The filter itself failing, in isolation |
| `test_forecast_written_end_to_end_respects_cutoff` | A persisted row whose recorded source (`orderbook_ref`) postdates its own cutoff — a forecast on a market it was entitled to forecast, built on evidence it was not |
| `test_leaked_snapshot_cannot_reach_a_written_row` | The firewall failing while market selection masks it |

The third exists because of a real finding: the two code-level guards cover for each other, so a
black-box run proves neither individually. An earlier version of the end-to-end test passed
against a deliberately broken firewall. Each test above was verified by mutation — the firewall
was replaced with a pass-through and each was confirmed to fail, then restored. A test that has
never been seen to fail is not evidence.

**What this does not cover.** Correct enforcement of a cutoff is not the same as the cutoff being
set to the right value. The runner stamps one cutoff per run, at run start, which makes the batch
checkable against a single timestamp — but nothing here detects a cutoff that is honestly
enforced and wrongly chosen. That is a review question, not a test question, and it is why the
cutoff contract is human-owned under CLAUDE.md's automation boundary.

## The naive baselines (month 1)

- **`market_mirror` v1.0.0** — `p_hat = mkt_yes_mid` at T-24h before close. Zero edge by
  construction. Exists to validate the pipeline end to end: if `market_mirror`'s Brier score
  isn't statistically indistinguishable from `brier_market`, something in the pipeline is
  broken, not the model.
- **`base_rate` v1.0.0** — `p_hat` = historical frequency of the outcome class. Genuinely naive;
  expected to lose to the market. The point is to have an honest floor.

Every later model (from month 5 onward) is judged against both.

## Venue coverage

Not every venue contributes every kind of data, and the asymmetry is reported rather than
smoothed over:

| Data | Kalshi | Polymarket |
|---|---|---|
| Markets, prices, trades, resolutions | yes | yes |
| Orderbook depth | **no** | yes |

Kalshi's depth endpoint is its only authenticated endpoint, and the account needed to obtain a
key pair is not available to this project's operator — `kalshi.com` is blocked from Portugal by
regulatory order, and Kalshi requires US residency. See
[ADR-0002](adr/0002-polymarket-as-depth-venue.md) for the full reasoning and what was verified.

The consequence for reading results: **any depth-derived metric** — effective spread,
depth-weighted mid, slippage estimate, book imbalance — **covers Polymarket only, and says so
wherever it is reported.** The headline scoring metrics below are unaffected, because they need
prices, trades, and resolutions, all of which both venues supply unauthenticated.

## Scoring

Scoring happens downstream, in the recomputable `forecast_scored` view
(`src/edgeledger/scoring/views.sql`), joining `forecast_log` against `resolutions` and
`closing_prices` at query time. The forecast row itself never learns the outcome.

Metrics, always reported as a pair (model vs. market baseline):

- **Brier score** (`brier` vs `brier_market`) — mean squared error of the probability forecast.
- **Log loss** — penalizes confident wrong calls more heavily than Brier.
- **Calibration** — do forecasts of "70%" resolve yes about 70% of the time, with a bootstrap CI.
- **Closing-line value (CLV)** — the market's own mid at forecast time minus its mid at close.
  This is the metric a desk trusts most, because it isolates timing skill from luck.

### Where `resolutions` and `closing_prices` come from

Both are built by `src/edgeledger/scoring/score.py`, which loads the log and bronze into DuckDB
and then applies the view. Neither is written back to disk: scoring is recomputable from the
log and bronze at any time, and must never mutate either.

**Resolutions** are looked up *by the market ids in the forecast log*, not by scanning
Polymarket's `closed=true` feed. That feed is returned oldest-first under plain offset
pagination, so a bounded scan only ever sees markets from 2020–2021 and never reaches anything
this project forecast — outcomes would accumulate forever and score nothing. Verified
2026-08-20. The Gamma filter is `condition_ids`; `conditionIds` and `condition_id` are silently
ignored and return an unrelated page, so a wrong parameter name fails open rather than loudly.

**Closing prices are derived, not fetched** — neither venue publishes a "closing price". The
closing mid is *the last market snapshot captured at or before the market's resolution
timestamp*, computed on the same bid/ask basis as the forecast-time mid (if the two used
different bases, their difference would not be CLV). Two consequences are reported rather than
hidden:

- Snapshots captured *after* resolution are excluded. A settled market prints 0 or 1, and
  admitting those would manufacture spectacular fake CLV — the most flattering possible bug.
- We only know what we captured. A market last snapshotted well before it settled has a stale
  closing price, so `close_lag_seconds` is stored alongside every row and a staleness threshold
  is logged. CLV aggregates should exclude implausibly stale rows, and say that they did.

No single-number "accuracy" is ever reported on its own — it's meaningless without the market
baseline alongside it.

## What's out of scope so far

No real forecasting model, no sizing/Kelly logic, no paper execution exists yet. This document
will grow a section per model version as they ship (month 3 onward: Elo/Bradley-Terry; month 5:
logistic regression; month 7: Poisson/Dixon-Coles; etc. — see the 12-month roadmap in the vault).
