"""Load the log + bronze into DuckDB and apply `views.sql` (month-01 spec §5).

The view in `views.sql` was written and tested long before anything could feed it. This
module is the missing input side: it materialises the three tables the view joins, then
runs the view over them.

Two of those tables are read straight off disk. The third, `closing_prices`, has no venue
endpoint behind it — a "closing price" is not something either venue publishes. It is
derived here, and the derivation is the one judgement call in this file:

  **The closing mid is the last market snapshot captured at or before the market's
  resolution timestamp.**

That is deliberately the *last observed* price, not the price at some fixed horizon before
close. We only know what we captured; a market that stopped being snapshotted a day before
it settled has a closing price a day stale, and `close_lag_seconds` is exposed so that
staleness is measurable rather than hidden. Rows whose lag is implausibly large should be
excluded from CLV aggregates by the caller — see `docs/methodology.md`.

Snapshots captured *after* resolution are excluded. Post-resolution prices are degenerate
(a settled market prints 0 or 1), and letting them through would manufacture spectacular
fake CLV — the single most flattering bug this project could ship.

ponytail: DuckDB reads the JSONL directly; no intermediate parquet/Delta step. Rebuild is
a few seconds over the whole log and stays greppable.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import duckdb

logger = logging.getLogger(__name__)

VIEWS_SQL = Path(__file__).with_name("views.sql")

# A closing price this far from resolution is too stale to be honest CLV. Not dropped
# here — flagged, so the exclusion is a reported choice rather than a silent filter.
DEFAULT_MAX_CLOSE_LAG_SECONDS = 7 * 24 * 3600


def _mid_from_payload_sql() -> str:
    """SQL mirroring `runner._mid_from_payload`: bestBid/bestAsk mid, else outcomePrices[0].

    Kept in SQL rather than looping in Python so the whole rebuild stays one query. The
    fallback ordering must match the runner's, or the closing mid would be computed on a
    different basis than the forecast-time mid it is differenced against — which would
    make CLV meaningless.
    """
    return """
        CASE
          WHEN TRY_CAST(json_extract_string(payload, '$.bestBid') AS DOUBLE) IS NOT NULL
           AND TRY_CAST(json_extract_string(payload, '$.bestAsk') AS DOUBLE) IS NOT NULL
          THEN (TRY_CAST(json_extract_string(payload, '$.bestBid') AS DOUBLE)
              + TRY_CAST(json_extract_string(payload, '$.bestAsk') AS DOUBLE)) / 2
          ELSE TRY_CAST(
                 json_extract_string(
                   TRY_CAST(json_extract_string(payload, '$.outcomePrices') AS JSON), '$[0]'
                 ) AS DOUBLE)
        END
    """


def build_connection(
    data_dir: Path,
    *,
    max_close_lag_seconds: int = DEFAULT_MAX_CLOSE_LAG_SECONDS,
) -> duckdb.DuckDBPyConnection:
    """Materialise `forecast_log`, `resolutions`, `closing_prices`, then create the view.

    Returns an in-memory connection. Nothing is written back to disk: scoring is
    recomputable from the log and bronze at any time, and must never mutate either
    (invariant 1).
    """
    con = duckdb.connect()
    log_path = data_dir / "forecast_log.jsonl"
    snapshot_glob = str(data_dir / "bronze" / "venue_market_snapshot" / "*" / "*.jsonl")
    resolution_glob = str(data_dir / "bronze" / "resolution" / "*" / "*.jsonl")

    if not log_path.exists():
        raise FileNotFoundError(f"no forecast log at {log_path}")

    # The probability columns are Decimal in the schema and therefore JSON *strings* on
    # disk — `str(Decimal)` is what keeps a row's hash stable (see forecast/log.py). That
    # makes DuckDB infer VARCHAR, so they are cast here rather than in views.sql: the view
    # is the tested contract and stays arithmetic-only.
    con.execute(
        """
        CREATE TABLE forecast_log AS
        SELECT * REPLACE (
          TRY_CAST(p_hat       AS DOUBLE) AS p_hat,
          TRY_CAST(mkt_yes_mid AS DOUBLE) AS mkt_yes_mid
        )
        FROM read_json_auto(?, format='newline_delimited')
        """,
        [str(log_path)],
    )

    # Bronze may legitimately be absent locally: the log is committed to git, bronze is
    # archived to object storage and gitignored. Empty tables keep the view runnable, and
    # every metric that needs them simply comes back NULL rather than the query failing.
    _create_or_empty(
        con,
        "resolutions_raw",
        resolution_glob,
        "venue VARCHAR, venue_market_id VARCHAR, resolved_outcome VARCHAR, "
        "resolution_ts_utc TIMESTAMPTZ, capture_ts_utc TIMESTAMPTZ",
    )
    _create_or_empty(
        con,
        "snapshots_raw",
        snapshot_glob,
        "venue VARCHAR, venue_market_id VARCHAR, capture_ts_utc TIMESTAMPTZ, payload VARCHAR",
    )

    # One resolution per market: the earliest, since a settled market keeps being polled
    # and re-ingested daily. Taking the latest would drift the closing-price cutoff
    # forward every day the market stays in the settled feed.
    # Timestamps are cast rather than trusted: bronze writes ISO-8601 with variable
    # fractional-second precision, which DuckDB infers as VARCHAR on a mixed batch.
    con.execute("""
        CREATE TABLE resolutions AS
        WITH typed AS (
          SELECT venue, venue_market_id, resolved_outcome,
                 TRY_CAST(resolution_ts_utc AS TIMESTAMPTZ) AS resolution_ts_utc
          FROM resolutions_raw
        )
        SELECT venue, venue_market_id,
               arg_min(resolved_outcome, resolution_ts_utc) AS resolved_outcome,
               min(resolution_ts_utc)                       AS resolution_ts_utc
        FROM typed
        WHERE resolution_ts_utc IS NOT NULL
        GROUP BY venue, venue_market_id
    """)

    con.execute(f"""
        CREATE TABLE closing_prices AS
        WITH priced AS (
          SELECT s.venue, s.venue_market_id,
                 TRY_CAST(s.capture_ts_utc AS TIMESTAMPTZ) AS capture_ts_utc,
                 {_mid_from_payload_sql()} AS mid
          FROM snapshots_raw s
        ),
        before_close AS (
          SELECT p.venue, p.venue_market_id, p.capture_ts_utc, p.mid, r.resolution_ts_utc
          FROM priced p
          JOIN resolutions r USING (venue, venue_market_id)
          -- The firewall for CLV: never a price observed after settlement.
          WHERE p.mid IS NOT NULL
            AND p.capture_ts_utc IS NOT NULL
            AND p.mid > 0 AND p.mid < 1
            AND p.capture_ts_utc <= r.resolution_ts_utc
        )
        SELECT venue, venue_market_id,
               arg_max(mid, capture_ts_utc)          AS close_yes_mid,
               max(capture_ts_utc)                   AS close_capture_ts_utc,
               date_diff('second', max(capture_ts_utc), any_value(resolution_ts_utc))
                                                     AS close_lag_seconds
        FROM before_close
        GROUP BY venue, venue_market_id
    """)

    con.execute(VIEWS_SQL.read_text(encoding="utf-8"))

    stale = con.execute(
        "SELECT count(*) FROM closing_prices WHERE close_lag_seconds > ?",
        [max_close_lag_seconds],
    ).fetchone()[0]
    if stale:
        logger.warning(
            "closing prices exceed the staleness threshold",
            extra={"stale_markets": stale, "threshold_seconds": max_close_lag_seconds},
        )

    return con


def _create_or_empty(
    con: duckdb.DuckDBPyConnection, table: str, glob: str, empty_ddl: str
) -> None:
    """Create `table` from a JSONL glob, or as an empty typed table when nothing matches."""
    try:
        con.execute(
            f"CREATE TABLE {table} AS "
            "SELECT * FROM read_json_auto(?, format='newline_delimited', union_by_name=true)",
            [glob],
        )
    except duckdb.IOException:
        # No files matched the glob — expected when bronze is not present locally.
        con.execute(f"CREATE TABLE {table} ({empty_ddl})")


def summarise(con: duckdb.DuckDBPyConnection) -> dict:
    """Headline numbers, always model-against-market (invariant 6).

    Every average is over rows where the metric is non-NULL, so unresolved and void
    markets drop out rather than being counted as zeros.
    """
    row = con.execute("""
        SELECT
          count(*)                                   AS forecasts,
          count(y)                                   AS scored,
          avg(brier)                                 AS brier,
          avg(brier_market)                          AS brier_market,
          avg(brier_delta)                           AS brier_delta,
          avg(log_loss)                              AS log_loss,
          avg(log_loss_market)                       AS log_loss_market,
          count(clv_signed)                          AS clv_observations,
          avg(clv_signed)                            AS clv_signed
        FROM forecast_scored
    """).fetchone()
    keys = (
        "forecasts", "scored", "brier", "brier_market", "brier_delta",
        "log_loss", "log_loss_market", "clv_observations", "clv_signed",
    )
    return dict(zip(keys, row, strict=True))


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Score the forecast log against the market.")
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument("--out", type=Path, help="write the JSON summary here")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

    con = build_connection(args.data_dir)
    summary = summarise(con)
    text = json.dumps(summary, indent=2, sort_keys=True, default=str)
    print(text)
    if args.out:
        args.out.write_text(text + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
