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

## The naive baselines (month 1)

- **`market_mirror` v1.0.0** — `p_hat = mkt_yes_mid` at T-24h before close. Zero edge by
  construction. Exists to validate the pipeline end to end: if `market_mirror`'s Brier score
  isn't statistically indistinguishable from `brier_market`, something in the pipeline is
  broken, not the model.
- **`base_rate` v1.0.0** — `p_hat` = historical frequency of the outcome class. Genuinely naive;
  expected to lose to the market. The point is to have an honest floor.

Every later model (from month 5 onward) is judged against both.

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

No single-number "accuracy" is ever reported on its own — it's meaningless without the market
baseline alongside it.

## What's out of scope so far

No real forecasting model, no sizing/Kelly logic, no paper execution exists yet. This document
will grow a section per model version as they ship (month 3 onward: Elo/Bradley-Terry; month 5:
logistic regression; month 7: Poisson/Dixon-Coles; etc. — see the 12-month roadmap in the vault).
