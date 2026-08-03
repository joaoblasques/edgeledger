"""Tests for the baseline forecast runner and the scoring view.

The runner is where the invariants meet real data, so these check the properties that
would silently invalidate the track record: zero-edge on the mirror, the point-in-time
cutoff, gapless seq, and never inventing a price.
"""

from __future__ import annotations

import json
import pathlib
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import duckdb
import pytest

from edgeledger.bronze.schemas import VenueMarketSnapshot
from edgeledger.bronze.writers import write_rows
from edgeledger.forecast.log import read_rows, verify_chain
from edgeledger.forecast.runner import run_market_mirror

NOW = datetime.now(UTC)


def _snapshot(market_id: str, *, bid: float | None, ask: float | None, when: datetime | None = None):
    payload: dict = {"question": f"Will {market_id} happen?", "conditionId": market_id}
    if bid is not None:
        payload["bestBid"] = bid
    if ask is not None:
        payload["bestAsk"] = ask
    ts = when or NOW
    return VenueMarketSnapshot(
        capture_ts_utc=ts,
        run_id="ingest-1",
        venue="polymarket",
        venue_market_id=market_id,
        payload=json.dumps(payload),
        ingest_date=ts.date(),
    )


def test_market_mirror_has_exactly_zero_edge(tmp_path):
    """The canary: p_hat must equal the mid, so any nonzero edge means a pipeline bug."""
    write_rows([_snapshot("m1", bid=0.40, ask=0.50)], tmp_path, run_id="ingest-1")

    assert run_market_mirror(tmp_path, run_id="fc-1") == 1

    row = read_rows(tmp_path)[0]
    assert row.p_hat == Decimal("0.45")
    assert row.mkt_yes_mid == Decimal("0.45")
    assert row.edge == Decimal(0)


def test_market_state_is_embedded_not_joined(tmp_path):
    """Invariant 2: bid/ask/mid/spread come from the snapshot at forecast time."""
    write_rows([_snapshot("m1", bid=0.40, ask=0.50)], tmp_path, run_id="ingest-1")
    run_market_mirror(tmp_path, run_id="fc-1")

    row = read_rows(tmp_path)[0]
    assert row.mkt_yes_bid == Decimal("0.40")
    assert row.mkt_yes_ask == Decimal("0.50")
    assert row.mkt_spread == Decimal("0.10")


def test_forecast_never_uses_data_after_its_cutoff(tmp_path):
    """Invariant 3: a snapshot captured after the run starts must not be forecast on."""
    future = NOW + timedelta(hours=1)
    write_rows(
        [_snapshot("past", bid=0.4, ask=0.5), _snapshot("future", bid=0.4, ask=0.5, when=future)],
        tmp_path,
        run_id="ingest-1",
    )

    run_market_mirror(tmp_path, run_id="fc-1")

    ids = {r.venue_market_id for r in read_rows(tmp_path)}
    assert "past" in ids
    assert "future" not in ids, "a future-dated snapshot leaked past the cutoff"


def test_every_forecast_cutoff_precedes_its_write(tmp_path):
    write_rows([_snapshot(f"m{i}", bid=0.4, ask=0.5) for i in range(3)], tmp_path, run_id="i-1")
    run_market_mirror(tmp_path, run_id="fc-1")

    for row in read_rows(tmp_path):
        assert row.feature_cutoff_ts_utc <= row.forecast_ts_utc


def test_seq_is_gapless_across_multiple_runs(tmp_path):
    """Invariant 5: a second run continues the one chain, it does not restart it.

    Each scheduled run re-forecasts every market it can see — that is the point of a
    6-hourly cadence, and it is why the count grows faster than the market count. What
    must hold is that seq stays gapless and monotonic across run boundaries.
    """
    write_rows([_snapshot("m1", bid=0.4, ask=0.5)], tmp_path, run_id="i-1")
    first = run_market_mirror(tmp_path, run_id="fc-1")

    write_rows([_snapshot("m2", bid=0.3, ask=0.4)], tmp_path, run_id="i-2")
    second = run_market_mirror(tmp_path, run_id="fc-2")

    rows = read_rows(tmp_path)
    assert [r.seq for r in rows] == list(range(first + second)), "gapless across runs"
    assert {r.run_id for r in rows} == {"fc-1", "fc-2"}, "both runs are represented"
    verify_chain(rows)


def test_market_without_a_price_is_skipped_not_defaulted(tmp_path):
    """A forecast of 0.5 "because we had nothing" is indistinguishable in the log from a
    genuine 0.5 belief. Skipping is the only honest option."""
    write_rows([_snapshot("no_price", bid=None, ask=None)], tmp_path, run_id="i-1")

    assert run_market_mirror(tmp_path, run_id="fc-1") == 0
    assert read_rows(tmp_path) == []


def test_only_the_newest_snapshot_per_market_is_forecast(tmp_path):
    """Two snapshots of one market in the window must yield one forecast, on the newer."""
    older = NOW - timedelta(minutes=30)
    write_rows(
        [_snapshot("m1", bid=0.10, ask=0.20, when=older), _snapshot("m1", bid=0.40, ask=0.50)],
        tmp_path,
        run_id="i-1",
    )

    assert run_market_mirror(tmp_path, run_id="fc-1") == 1
    assert read_rows(tmp_path)[0].p_hat == Decimal("0.45")


def test_chain_verifies_after_a_run(tmp_path):
    write_rows([_snapshot(f"m{i}", bid=0.4, ask=0.5) for i in range(5)], tmp_path, run_id="i-1")
    run_market_mirror(tmp_path, run_id="fc-1")

    verify_chain(read_rows(tmp_path))


# --- scoring view ---------------------------------------------------------------------


@pytest.fixture
def scored_db():
    con = duckdb.connect()
    con.execute("""
        CREATE TABLE forecast_log (
          venue VARCHAR, venue_market_id VARCHAR, p_hat DOUBLE, mkt_yes_mid DOUBLE);
        CREATE TABLE resolutions (
          venue VARCHAR, venue_market_id VARCHAR, resolved_outcome VARCHAR);
        CREATE TABLE closing_prices (
          venue VARCHAR, venue_market_id VARCHAR, close_yes_mid DOUBLE);
    """)
    sql = pathlib.Path("src/edgeledger/scoring/views.sql").read_text()
    return con, sql


def test_scoring_view_computes_brier_against_market(scored_db):
    con, sql = scored_db
    con.execute("""
        INSERT INTO forecast_log VALUES ('polymarket','m1',0.70,0.60);
        INSERT INTO resolutions VALUES ('polymarket','m1','yes');
        INSERT INTO closing_prices VALUES ('polymarket','m1',0.75);
    """)
    con.execute(sql)

    brier, brier_market, delta = con.execute(
        "SELECT brier, brier_market, brier_delta FROM forecast_scored"
    ).fetchone()

    assert brier == pytest.approx(0.09)  # (0.70 - 1)^2
    assert brier_market == pytest.approx(0.16)  # (0.60 - 1)^2
    assert delta < 0, "model beat the market here"


def test_void_settlement_drops_out_of_scoring(scored_db):
    """'invalid' must not be scored as a loss — it is not an outcome."""
    con, sql = scored_db
    con.execute("""
        INSERT INTO forecast_log VALUES ('polymarket','m1',0.90,0.90);
        INSERT INTO resolutions VALUES ('polymarket','m1','invalid');
        INSERT INTO closing_prices VALUES ('polymarket','m1',0.90);
    """)
    con.execute(sql)

    y, brier = con.execute("SELECT y, brier FROM forecast_scored").fetchone()
    assert y is None
    assert brier is None


def test_log_loss_is_finite_for_a_confident_wrong_call(scored_db):
    """LN(0) is -inf; one unguarded overconfident forecast would destroy the aggregate."""
    con, sql = scored_db
    con.execute("""
        INSERT INTO forecast_log VALUES ('polymarket','m1',0.0,0.5);
        INSERT INTO resolutions VALUES ('polymarket','m1','yes');
        INSERT INTO closing_prices VALUES ('polymarket','m1',0.5);
    """)
    con.execute(sql)

    (log_loss,) = con.execute("SELECT log_loss FROM forecast_scored").fetchone()
    assert log_loss is not None
    assert log_loss < 100, "must be clamped, not infinite"


def test_clv_signed_flips_for_a_no_leaning_forecast(scored_db):
    """Unsigned CLV reads backwards when the forecast leans 'no'."""
    con, sql = scored_db
    con.execute("""
        INSERT INTO forecast_log VALUES ('polymarket','yes_lean',0.70,0.60),
                                        ('polymarket','no_lean', 0.30,0.60);
        INSERT INTO resolutions VALUES ('polymarket','yes_lean','yes'),
                                       ('polymarket','no_lean','no');
        INSERT INTO closing_prices VALUES ('polymarket','yes_lean',0.75),
                                          ('polymarket','no_lean',0.50);
    """)
    con.execute(sql)

    rows = dict(
        con.execute("SELECT venue_market_id, clv_signed FROM forecast_scored").fetchall()
    )
    # Yes-lean: price moved toward us (0.60 -> 0.75), so signed CLV is positive.
    assert rows["yes_lean"] == pytest.approx(0.15)
    # No-lean: price fell (0.60 -> 0.50), which is also in our favour.
    assert rows["no_lean"] == pytest.approx(0.10)
