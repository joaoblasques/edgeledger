-- forecast_scored view DDL. STUB — due week 4 (month-01 spec §5).
-- Recomputable, downstream of forecast_log + resolutions + closing_prices.
-- brier_market is non-negotiable: every metric ever reported is a delta against it
-- (CLAUDE.md invariant 6).

CREATE VIEW forecast_scored AS
SELECT
  f.*,
  r.resolved_outcome,
  CASE WHEN r.resolved_outcome = 'yes' THEN 1 ELSE 0 END AS y,
  POWER(f.p_hat - y, 2)                    AS brier,
  POWER(f.mkt_yes_mid - y, 2)              AS brier_market,   -- the baseline
  -(y*LN(f.p_hat) + (1-y)*LN(1-f.p_hat))   AS log_loss,
  c.close_yes_mid,
  f.mkt_yes_mid - c.close_yes_mid          AS clv             -- closing line value
FROM forecast_log f
LEFT JOIN resolutions r  USING (venue, venue_market_id)
LEFT JOIN closing_prices c USING (venue, venue_market_id);
