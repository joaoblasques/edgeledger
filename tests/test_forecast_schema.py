"""Executable spec for forecast/schema.py — the one fully-implemented module.

These should all pass today; schema.py is not a stub.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError

from edgeledger.forecast.schema import ForecastLogRow

NOW = datetime.now(UTC)
CUTOFF = NOW - timedelta(seconds=1)


def _make_row(**overrides) -> ForecastLogRow:
    fields = {
        "forecast_id": uuid4(),
        "seq": 0,
        "forecast_ts_utc": NOW,
        "model_name": "market_mirror",
        "model_version": "1.0.0",
        "code_git_sha": "deadbeef",
        "run_id": "run-1",
        "venue": "kalshi",
        "venue_market_id": "TICKER-1",
        "market_question": "Will X happen?",
        "outcome_side": "yes",
        "p_hat": Decimal("0.55"),
        "feature_cutoff_ts_utc": CUTOFF,
        "feature_vector": "{}",
        "feature_set_version": "v1",
        "row_hash": "abc",
        "prev_row_hash": "genesis",
    }
    fields.update(overrides)
    return ForecastLogRow(**fields)


def test_valid_row_constructs():
    row = _make_row()
    assert row.p_hat == Decimal("0.55")


def test_row_is_immutable():
    row = _make_row()
    with pytest.raises(ValidationError):
        row.p_hat = Decimal("0.9")


def test_naive_datetime_rejected():
    with pytest.raises(ValidationError):
        _make_row(forecast_ts_utc=datetime.now())  # noqa: DTZ005 — intentionally naive, asserting rejection


def test_p_hat_out_of_range_rejected():
    with pytest.raises(ValidationError):
        _make_row(p_hat=Decimal("1.5"))


def test_negative_seq_rejected():
    with pytest.raises(ValidationError):
        _make_row(seq=-1)


def test_feature_cutoff_after_forecast_ts_rejected():
    """The leakage firewall at the type level: a cutoff can't be later than the
    forecast it's supposed to gate."""
    with pytest.raises(ValidationError):
        _make_row(feature_cutoff_ts_utc=NOW + timedelta(seconds=1))


def test_p_hat_interval_bounds_must_be_ordered():
    with pytest.raises(ValidationError):
        _make_row(p_hat_lo=Decimal("0.9"), p_hat_hi=Decimal("0.1"))


def test_nullable_fields_default_to_none():
    row = _make_row()
    assert row.canonical_market_id is None
    assert row.mkt_yes_bid is None
    assert row.supersedes_forecast_id is None
