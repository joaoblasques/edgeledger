-- forecast_scored — the recomputable scoring view (month-01 spec §5).
--
-- Downstream of forecast_log + resolutions + closing_prices, joined at QUERY time. The
-- forecast row itself never learns the outcome (invariant 1): scoring is derived, never
-- written back.
--
-- brier_market is non-negotiable. Every metric reported anywhere is a delta against it
-- (invariant 6) — a raw Brier score with no baseline is meaningless, because a book of
-- mostly-longshot contracts flatters any model that simply always guesses low.
--
-- Written for DuckDB. The CTE is required, not stylistic: `y` cannot be referenced by the
-- same SELECT that defines it.

CREATE OR REPLACE VIEW forecast_scored AS
WITH scored AS (
  SELECT
    f.*,
    r.resolved_outcome,
    -- Only 'yes'/'no' are scoreable. 'invalid' (a void settlement) becomes NULL and drops
    -- out of every metric below, rather than being silently counted as a loss.
    CASE r.resolved_outcome
      WHEN 'yes' THEN 1.0
      WHEN 'no'  THEN 0.0
      ELSE NULL
    END                                            AS y,
    c.close_yes_mid
  FROM forecast_log f
  LEFT JOIN resolutions    r USING (venue, venue_market_id)
  LEFT JOIN closing_prices c USING (venue, venue_market_id)
)
SELECT
  scored.*,

  -- Brier: mean squared error of the probability forecast. Lower is better.
  POWER(p_hat - y, 2)                              AS brier,

  -- The baseline every number is judged against: the market's own mid, scored identically.
  POWER(mkt_yes_mid - y, 2)                        AS brier_market,

  -- Negative means the model beat the market on this forecast.
  POWER(p_hat - y, 2) - POWER(mkt_yes_mid - y, 2)  AS brier_delta,

  -- Log loss punishes confident wrong calls far harder than Brier. p_hat is clamped away
  -- from 0 and 1 because LN(0) is -inf: a single overconfident forecast would otherwise
  -- make the aggregate infinite and destroy the metric for every other row.
  -(
    y * LN(GREATEST(p_hat, 1e-15))
    + (1 - y) * LN(GREATEST(1 - p_hat, 1e-15))
  )                                                AS log_loss,

  -(
    y * LN(GREATEST(mkt_yes_mid, 1e-15))
    + (1 - y) * LN(GREATEST(1 - mkt_yes_mid, 1e-15))
  )                                                AS log_loss_market,

  -- Closing-line value: the market's mid when we forecast, against its mid at close. The
  -- metric a desk trusts most — it isolates timing skill from luck, and is measurable
  -- long before enough contracts have resolved to say anything about Brier.
  mkt_yes_mid - close_yes_mid                      AS clv,

  -- Signed by the side we took, so positive always means "we got the better price".
  -- Unsigned CLV on a 'no'-leaning forecast reads backwards.
  CASE WHEN p_hat >= mkt_yes_mid
       THEN close_yes_mid - mkt_yes_mid
       ELSE mkt_yes_mid - close_yes_mid
  END                                              AS clv_signed

FROM scored;
