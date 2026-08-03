"""Tests for bronze writers — mostly about the idempotency contract.

A retried Airflow task must not double-count its own rows, and must never delete a
sibling run's work. Those two failure modes are what these tests exist to prevent.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from edgeledger.bronze.schemas import Resolution, VenueMarketSnapshot, VenueTrade
from edgeledger.bronze.writers import read_rows, read_since, write_rows

NOW = datetime.now(UTC)


def _snap(market_id: str = "0xabc", *, run_id: str = "r1", when: datetime | None = None):
    ts = when or NOW
    return VenueMarketSnapshot(
        capture_ts_utc=ts,
        run_id=run_id,
        venue="polymarket",
        venue_market_id=market_id,
        payload='{"x":1}',
        ingest_date=ts.date(),
    )


def test_rerunning_a_task_does_not_duplicate_rows(tmp_path):
    """The core idempotency case: same run_id, same rows, written twice."""
    rows = [_snap("m1"), _snap("m2")]

    write_rows(rows, tmp_path, run_id="run-a")
    write_rows(rows, tmp_path, run_id="run-a")

    stored = read_rows(VenueMarketSnapshot, tmp_path)
    assert len(stored) == 2, "a retry must replace its partition, not append to it"


def test_a_rerun_never_clobbers_another_runs_rows(tmp_path):
    """Two runs on the same ingest_date are independent; retrying one must not
    delete the other's data."""
    write_rows([_snap("m1", run_id="run-a")], tmp_path, run_id="run-a")
    write_rows([_snap("m2", run_id="run-b")], tmp_path, run_id="run-b")

    # run-a retries.
    write_rows([_snap("m1", run_id="run-a")], tmp_path, run_id="run-a")

    ids = sorted(r.venue_market_id for r in read_rows(VenueMarketSnapshot, tmp_path))
    assert ids == ["m1", "m2"], "run-b's row must survive run-a's retry"


def test_partitions_are_split_by_ingest_date(tmp_path):
    yesterday = NOW - timedelta(days=1)
    write_rows(
        [_snap("m1"), _snap("m2", when=yesterday)],
        tmp_path,
        run_id="run-a",
    )

    assert len(read_rows(VenueMarketSnapshot, tmp_path)) == 2
    assert len(read_rows(VenueMarketSnapshot, tmp_path, day=NOW.date())) == 1
    assert len(read_rows(VenueMarketSnapshot, tmp_path, day=yesterday.date())) == 1


def test_empty_write_is_a_noop(tmp_path):
    assert write_rows([], tmp_path, run_id="run-a") == 0
    assert read_rows(VenueMarketSnapshot, tmp_path) == []


def test_mixed_row_types_are_rejected(tmp_path):
    """A heterogeneous batch would write two schemas into one partition file."""
    trade = VenueTrade(
        capture_ts_utc=NOW,
        venue="polymarket",
        venue_market_id="m1",
        venue_trade_id="t1",
        trade_ts_utc=NOW,
        price=Decimal("0.55"),
        size=Decimal(10),
        payload="{}",
        ingest_date=NOW.date(),
    )
    with pytest.raises(TypeError):
        write_rows([_snap("m1"), trade], tmp_path, run_id="run-a")


def test_resolution_partitions_on_capture_ts(tmp_path):
    """Resolution has no ingest_date column — the partition comes from our own clock."""
    res = Resolution(
        capture_ts_utc=NOW,
        venue="polymarket",
        venue_market_id="m1",
        resolved_outcome="yes",
        resolution_ts_utc=NOW - timedelta(hours=2),
        payload="{}",
    )
    assert write_rows([res], tmp_path, run_id="run-a") == 1

    stored = read_rows(Resolution, tmp_path)
    assert len(stored) == 1
    # Invariant 8: the two timestamps stay distinct.
    assert stored[0].capture_ts_utc != stored[0].resolution_ts_utc


def test_round_trip_preserves_types(tmp_path):
    """Decimal and datetime must survive JSON serialisation unchanged."""
    trade = VenueTrade(
        capture_ts_utc=NOW,
        venue="kalshi",
        venue_market_id="T-1",
        venue_trade_id="t1",
        trade_ts_utc=NOW - timedelta(seconds=30),
        price=Decimal("0.0455"),
        size=Decimal("628.35"),
        payload='{"raw":true}',
        ingest_date=NOW.date(),
    )
    write_rows([trade], tmp_path, run_id="run-a")

    got = read_rows(VenueTrade, tmp_path)[0]
    assert got.price == Decimal("0.0455")
    assert got.size == Decimal("628.35")
    assert got.capture_ts_utc == NOW
    assert got.trade_ts_utc == trade.trade_ts_utc


def test_read_since_filters_by_capture_date(tmp_path):
    old = NOW - timedelta(days=5)
    write_rows([_snap("old", when=old), _snap("new")], tmp_path, run_id="run-a")

    recent = read_since(VenueMarketSnapshot, tmp_path, since=(NOW - timedelta(days=1)).date())
    assert [r.venue_market_id for r in recent] == ["new"]


def test_run_id_with_path_separators_is_sanitised(tmp_path):
    """An Airflow run_id can contain characters that would escape the partition dir."""
    write_rows([_snap("m1")], tmp_path, run_id="scheduled__2026-08-03T00:00:00+00:00")
    assert len(read_rows(VenueMarketSnapshot, tmp_path)) == 1
