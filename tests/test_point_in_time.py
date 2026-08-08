"""Executable spec for the leakage firewall (CLAUDE.md invariant 3): every feature in
`feature_vector` must be derivable only from bronze rows with
capture_ts_utc <= feature_cutoff_ts_utc.

The schema-level check (feature_cutoff_ts_utc <= forecast_ts_utc) already passes —
see test_forecast_schema.py::test_feature_cutoff_after_forecast_ts_rejected. This
file specs the DEEPER check that needs the bronze layer and feature builder, both
still stubs: that the feature_vector's actual source rows respect the cutoff. These
are EXPECTED TO FAIL until bronze/writers.py and a feature builder exist (week 2-4).
"""

import json
from datetime import UTC, datetime, timedelta

from edgeledger.bronze.schemas import VenueMarketSnapshot
from edgeledger.bronze.writers import write_rows
from edgeledger.forecast import runner as runner_module
from edgeledger.forecast.log import read_rows
from edgeledger.forecast.runner import run_market_mirror


def test_feature_builder_excludes_data_after_cutoff():
    """The feature builder must refuse to include any bronze row whose capture_ts_utc
    is after the requested feature_cutoff_ts_utc — this is the actual leakage
    firewall, not just the schema-level ordering check."""
    from edgeledger.bronze.schemas import VenueMarketSnapshot
    from edgeledger.forecast.baselines import build_feature_vector  # not yet defined

    cutoff = datetime.now(UTC)
    stale_ok = VenueMarketSnapshot(
        capture_ts_utc=cutoff - timedelta(minutes=1),
        run_id="r1",
        venue="kalshi",
        venue_market_id="T-1",
        payload="{}",
        ingest_date=cutoff.date(),
    )
    leaked = VenueMarketSnapshot(
        capture_ts_utc=cutoff + timedelta(minutes=1),
        run_id="r2",
        venue="kalshi",
        venue_market_id="T-1",
        payload="{}",
        ingest_date=cutoff.date(),
    )

    features = build_feature_vector(
        snapshots=[stale_ok, leaked],
        feature_cutoff_ts_utc=cutoff,
    )

    assert leaked.capture_ts_utc not in [s.capture_ts_utc for s in features.source_snapshots]
    assert stale_ok.capture_ts_utc in [s.capture_ts_utc for s in features.source_snapshots]


def test_forecast_written_end_to_end_respects_cutoff(tmp_path):
    """Integration spec: a forecast produced by the pipeline never embeds a feature
    sourced from data captured after its own feature_cutoff_ts_utc. This is the test
    month-01 spec §10 calls the leakage firewall assertion.

    Distinct from test_forecast_runner.py::test_forecast_never_uses_data_after_its_cutoff,
    which checks *selection* — that a future-dated market is not forecast at all. This
    checks *provenance*: for every row actually persisted, the snapshot it says it used
    (`orderbook_ref`) was captured at or before the cutoff it claims. A row that names a
    market it was entitled to forecast, but attaches evidence from after its own cutoff,
    passes the selection test and is exactly the leak that survives review.
    """
    now = datetime.now(UTC)

    def snapshot(market_id: str, when: datetime) -> VenueMarketSnapshot:
        return VenueMarketSnapshot(
            capture_ts_utc=when,
            run_id="ingest-1",
            venue="polymarket",
            venue_market_id=market_id,
            payload=json.dumps(
                {"question": f"Will {market_id} happen?", "bestBid": 0.40, "bestAsk": 0.50}
            ),
            ingest_date=when.date(),
        )

    # Each market has a legitimate pre-cutoff snapshot AND a post-cutoff one. The runner
    # picks the newest at-or-before the cutoff, so the later row must never be the source.
    write_rows(
        [
            snapshot("m1", now - timedelta(minutes=30)),
            snapshot("m1", now + timedelta(minutes=30)),
            snapshot("m2", now - timedelta(minutes=5)),
            snapshot("m2", now + timedelta(hours=2)),
        ],
        tmp_path,
        run_id="ingest-1",
    )

    assert run_market_mirror(tmp_path, run_id="fc-1") == 2

    rows = read_rows(tmp_path)
    assert len(rows) == 2, "the run must write one row per market, or nothing is asserted"

    for row in rows:
        assert row.orderbook_ref is not None, "no provenance recorded — cutoff unprovable"
        source_capture = datetime.fromisoformat(row.orderbook_ref)
        assert source_capture <= row.feature_cutoff_ts_utc, (
            f"{row.venue_market_id} was built from data captured at {source_capture}, "
            f"after its own cutoff {row.feature_cutoff_ts_utc} — leakage"
        )
        assert row.feature_cutoff_ts_utc <= row.forecast_ts_utc

        # The row must be built from the PRE-cutoff snapshot, not merely from some row
        # that happens to predate the cutoff. Each market above has a legitimate snapshot
        # and a post-cutoff one; if the later row were used, the recorded price would
        # still look valid, so only the capture stamp distinguishes them.
        assert source_capture < now, (
            f"{row.venue_market_id} sourced a post-cutoff snapshot captured at "
            f"{source_capture} (test baseline {now})"
        )


def test_leaked_snapshot_cannot_reach_a_written_row(tmp_path):
    """The firewall must hold even if market selection lets a future row through.

    `run_market_mirror` guards twice: it filters future snapshots when picking the newest
    per market, and `build_feature_vector` filters again. Defence in depth is right, but
    it means neither guard alone is proven by a black-box run — the other covers for it.
    This test removes the outer guard and asserts the inner one still refuses to write.
    """
    now = datetime.now(UTC)
    captured = now - timedelta(minutes=10)

    # The snapshot is in the past, so market selection admits it — the outer guard is
    # satisfied and cannot mask the result. The firewall then receives a cutoff EARLIER
    # than the capture, which is the leak it exists to stop.
    write_rows(
        [
            VenueMarketSnapshot(
                capture_ts_utc=captured,
                run_id="ingest-1",
                venue="polymarket",
                venue_market_id="stale_vs_cutoff",
                payload=json.dumps({"question": "leaked?", "bestBid": 0.4, "bestAsk": 0.5}),
                ingest_date=captured.date(),
            )
        ],
        tmp_path,
        run_id="ingest-1",
    )

    original = runner_module.build_feature_vector
    seen: list[int] = []

    def spy(snapshots, feature_cutoff_ts_utc, features=None):
        seen.append(len(snapshots))
        return original(
            snapshots,
            feature_cutoff_ts_utc=captured - timedelta(minutes=5),
            features=features,
        )

    runner_module.build_feature_vector = spy
    try:
        written = run_market_mirror(tmp_path, run_id="fc-1")
    finally:
        runner_module.build_feature_vector = original

    assert seen, "build_feature_vector was never reached — the test proved nothing"
    assert written == 0, "a post-cutoff snapshot produced a forecast row"
    assert read_rows(tmp_path) == []
