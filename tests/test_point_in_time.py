"""Executable spec for the leakage firewall (CLAUDE.md invariant 3): every feature in
`feature_vector` must be derivable only from bronze rows with
capture_ts_utc <= feature_cutoff_ts_utc.

The schema-level check (feature_cutoff_ts_utc <= forecast_ts_utc) already passes —
see test_forecast_schema.py::test_feature_cutoff_after_forecast_ts_rejected. This
file specs the DEEPER check that needs the bronze layer and feature builder, both
still stubs: that the feature_vector's actual source rows respect the cutoff. These
are EXPECTED TO FAIL until bronze/writers.py and a feature builder exist (week 2-4).
"""

from datetime import UTC, datetime, timedelta

import pytest


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
    month-01 spec §10 calls the leakage firewall assertion."""

    pytest.skip("pipeline not implemented — spec only, see month-01 spec §10 item 5")
