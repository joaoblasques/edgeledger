"""Tests for the scoring inputs — the tables `views.sql` joins but never builds.

`tests/test_forecast_runner.py` already covers the metric arithmetic against synthetic
tables. What is tested here is the part that had no coverage: deriving `closing_prices`
from bronze, and the exclusions that keep CLV honest.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest

from edgeledger.bronze.schemas import Resolution, VenueMarketSnapshot
from edgeledger.bronze.writers import write_rows
from edgeledger.forecast.log import append_forecast
from edgeledger.forecast.schema import ForecastLogRow
from edgeledger.scoring.score import build_connection, summarise

BASE = datetime(2026, 8, 1, 12, 0, tzinfo=UTC)


def _snapshot(market: str, *, bid: float, ask: float, at: datetime) -> VenueMarketSnapshot:
    return VenueMarketSnapshot(
        capture_ts_utc=at,
        run_id="ingest-1",
        venue="polymarket",
        venue_market_id=market,
        payload=json.dumps({"bestBid": bid, "bestAsk": ask, "question": f"Q {market}?"}),
        ingest_date=at.date(),
    )


def _resolution(market: str, outcome: str, *, at: datetime) -> Resolution:
    return Resolution(
        capture_ts_utc=at,
        venue="polymarket",
        venue_market_id=market,
        resolved_outcome=outcome,
        resolution_ts_utc=at,
        payload="{}",
    )


def _forecast(tmp_path, market: str, *, p_hat: str, mid: str, seq: int) -> None:
    from decimal import Decimal
    from uuid import uuid4

    append_forecast(
        ForecastLogRow(
            forecast_id=uuid4(),
            seq=seq,
            forecast_ts_utc=BASE,
            model_name="market_mirror",
            model_version="1.0.0",
            code_git_sha="deadbeef",
            run_id="fc-1",
            venue="polymarket",
            venue_market_id=market,
            market_question=f"Q {market}?",
            outcome_side="yes",
            p_hat=Decimal(p_hat),
            mkt_yes_mid=Decimal(mid),
            orderbook_ref=BASE.isoformat(),
            feature_cutoff_ts_utc=BASE,
            feature_vector="{}",
            feature_set_version="v1",
            edge=Decimal(p_hat) - Decimal(mid),
            row_hash="pending",
            prev_row_hash="pending",
        ),
        tmp_path,
    )


@pytest.fixture
def scored(tmp_path):
    """One market: forecast at 0.60 mid, drifts to 0.80, resolves 'yes'."""
    _forecast(tmp_path, "m1", p_hat="0.70", mid="0.60", seq=0)
    write_rows(
        [
            _snapshot("m1", bid=0.55, ask=0.65, at=BASE),
            _snapshot("m1", bid=0.75, ask=0.85, at=BASE + timedelta(days=2)),
        ],
        tmp_path,
        run_id="ingest-1",
    )
    write_rows(
        [_resolution("m1", "yes", at=BASE + timedelta(days=3))], tmp_path, run_id="res-1"
    )
    return build_connection(tmp_path)


def test_closing_price_is_the_last_snapshot_before_resolution(scored):
    close, lag = scored.execute(
        "SELECT close_yes_mid, close_lag_seconds FROM closing_prices"
    ).fetchone()
    assert close == pytest.approx(0.80)  # the later snapshot, not the earlier 0.60
    assert lag == 86400  # one day between last capture and resolution


def test_metrics_compute_end_to_end(scored):
    s = summarise(scored)
    assert s["scored"] == 1
    assert s["brier"] == pytest.approx(0.09)  # (0.70 - 1)^2
    assert s["brier_market"] == pytest.approx(0.16)  # (0.60 - 1)^2
    assert s["brier_delta"] < 0
    # Forecast leaned yes and the price rose 0.60 -> 0.80: signed CLV is positive.
    assert s["clv_signed"] == pytest.approx(0.20)


def test_post_resolution_snapshots_never_set_the_closing_price(tmp_path):
    """A settled market prints ~0 or ~1. Letting that through manufactures fake CLV."""
    _forecast(tmp_path, "m1", p_hat="0.70", mid="0.60", seq=0)
    write_rows(
        [
            _snapshot("m1", bid=0.55, ask=0.65, at=BASE),
            # After settlement, the book collapses to certainty.
            _snapshot("m1", bid=0.99, ask=0.999, at=BASE + timedelta(days=5)),
        ],
        tmp_path,
        run_id="ingest-1",
    )
    write_rows(
        [_resolution("m1", "yes", at=BASE + timedelta(days=3))], tmp_path, run_id="res-1"
    )
    con = build_connection(tmp_path)

    (close,) = con.execute("SELECT close_yes_mid FROM closing_prices").fetchone()
    assert close == pytest.approx(0.60), "post-resolution price must be excluded"
    assert summarise(con)["clv_signed"] == pytest.approx(0.0)


def test_unresolved_markets_are_not_scored(tmp_path):
    """No resolution means no Brier — never a silently-zero score."""
    _forecast(tmp_path, "m1", p_hat="0.70", mid="0.60", seq=0)
    write_rows([_snapshot("m1", bid=0.55, ask=0.65, at=BASE)], tmp_path, run_id="ingest-1")

    s = summarise(build_connection(tmp_path))
    assert s["forecasts"] == 1
    assert s["scored"] == 0
    assert s["brier"] is None


def test_repeated_resolution_ingests_do_not_drift_the_cutoff(tmp_path):
    """A settled market is re-polled daily; the earliest resolution ts must win."""
    _forecast(tmp_path, "m1", p_hat="0.70", mid="0.60", seq=0)
    write_rows([_snapshot("m1", bid=0.55, ask=0.65, at=BASE)], tmp_path, run_id="ingest-1")
    for day, run in ((3, "res-1"), (4, "res-2"), (5, "res-3")):
        write_rows(
            [_resolution("m1", "yes", at=BASE + timedelta(days=day))], tmp_path, run_id=run
        )

    con = build_connection(tmp_path)
    assert con.execute("SELECT count(*) FROM resolutions").fetchone()[0] == 1
    (lag,) = con.execute("SELECT close_lag_seconds FROM closing_prices").fetchone()
    assert lag == 3 * 86400, "cutoff must anchor to the first observed resolution"


def test_missing_bronze_degrades_to_nulls_not_a_crash(tmp_path):
    """Bronze is gitignored and archived off-box; scoring must still run on the log alone."""
    _forecast(tmp_path, "m1", p_hat="0.70", mid="0.60", seq=0)

    s = summarise(build_connection(tmp_path))
    assert s["forecasts"] == 1
    assert s["scored"] == 0


# --- resolution lookup ------------------------------------------------------------------


def test_forecast_market_ids_are_deduped_newest_first(tmp_path):
    """The poll list comes off the log, most recently forecast first."""
    from edgeledger.ingest import forecast_market_ids

    _forecast(tmp_path, "m1", p_hat="0.70", mid="0.60", seq=0)
    _forecast(tmp_path, "m2", p_hat="0.40", mid="0.40", seq=1)
    _forecast(tmp_path, "m1", p_hat="0.75", mid="0.65", seq=2)  # re-forecast

    assert forecast_market_ids(tmp_path, venue="polymarket") == ["m2", "m1"]
    assert forecast_market_ids(tmp_path, venue="kalshi") == []


def test_forecast_market_ids_on_a_missing_log(tmp_path):
    from edgeledger.ingest import forecast_market_ids

    assert forecast_market_ids(tmp_path, venue="polymarket") == []


def test_targeted_ingest_polls_log_ids_and_skips_open_markets(tmp_path, monkeypatch):
    """Regression: the closed-feed scan is oldest-first and never reaches our markets.

    Also pins the parameter name — Gamma *silently ignores* `conditionIds`/`condition_id`
    and returns an unrelated page, so a wrong name fails open rather than loudly.
    """
    import asyncio

    from edgeledger.clients.base import Captured
    from edgeledger.ingest import ingest_polymarket_resolutions_for_forecast_markets

    _forecast(tmp_path, "settled", p_hat="0.70", mid="0.60", seq=0)
    _forecast(tmp_path, "still_open", p_hat="0.40", mid="0.40", seq=1)

    asked: list[list[str]] = []

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def list_markets(self, *, condition_ids, limit):
            asked.append(list(condition_ids))
            return Captured(
                capture_ts_utc=BASE,
                payload=[
                    {
                        "conditionId": "settled",
                        "closed": True,
                        "umaResolutionStatus": "resolved",
                        "outcomePrices": '["1","0"]',
                        "endDate": "2026-08-03T00:00:00Z",
                    },
                    {
                        "conditionId": "still_open",
                        "closed": False,
                        "outcomePrices": '["0.4","0.6"]',
                    },
                ],
            )

    monkeypatch.setattr("edgeledger.ingest.PolymarketClient", FakeClient)

    written = asyncio.run(
        ingest_polymarket_resolutions_for_forecast_markets(tmp_path, run_id="res-1")
    )

    assert written == 1, "only the settled market yields a resolution"
    assert asked == [["still_open", "settled"]], "must poll the log's ids, newest first"

    con = build_connection(tmp_path)
    outcome = con.execute("SELECT resolved_outcome FROM resolutions").fetchall()
    assert outcome == [("yes",)]
