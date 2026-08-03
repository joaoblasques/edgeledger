"""Executable spec for the hash chain (CLAUDE.md invariant 4).

forecast/log.py is a stub — these are EXPECTED TO FAIL (ImportError/AttributeError)
until it's implemented in week 3. They exist now so the implementation has a target.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from edgeledger.forecast.schema import ForecastLogRow

NOW = datetime.now(UTC)


def _make_row(prev_row_hash: str, seq: int) -> ForecastLogRow:
    return ForecastLogRow(
        forecast_id=uuid4(),
        seq=seq,
        forecast_ts_utc=NOW,
        model_name="market_mirror",
        model_version="1.0.0",
        code_git_sha="deadbeef",
        run_id="run-1",
        venue="kalshi",
        venue_market_id="TICKER-1",
        market_question="Will X happen?",
        outcome_side="yes",
        p_hat=Decimal("0.55"),
        feature_cutoff_ts_utc=NOW - timedelta(seconds=1),
        feature_vector="{}",
        feature_set_version="v1",
        row_hash="placeholder",
        prev_row_hash=prev_row_hash,
    )


def test_row_hash_is_sha256_of_prev_hash_and_canonical_json():
    from edgeledger.forecast.log import canonical_json, compute_row_hash

    row = _make_row(prev_row_hash="genesis", seq=0)
    expected = compute_row_hash(row.prev_row_hash, row)
    import hashlib

    assert expected == hashlib.sha256(
        (row.prev_row_hash + canonical_json(row)).encode()
    ).hexdigest()


def test_chain_breaks_if_any_row_is_altered():
    """Tamper evidence: changing any row invalidates every hash after it."""
    from edgeledger.forecast.log import compute_row_hash

    row_a = _make_row(prev_row_hash="genesis", seq=0)
    hash_a = compute_row_hash(row_a.prev_row_hash, row_a)

    row_b = _make_row(prev_row_hash=hash_a, seq=1)
    hash_b = compute_row_hash(row_b.prev_row_hash, row_b)

    tampered_a = row_a.model_copy(update={"p_hat": Decimal("0.99")})
    tampered_hash_a = compute_row_hash(tampered_a.prev_row_hash, tampered_a)

    assert tampered_hash_a != hash_a
    recomputed_hash_b = compute_row_hash(tampered_hash_a, row_b)
    assert recomputed_hash_b != hash_b


def test_append_forecast_never_updates_or_deletes(tmp_path):
    """Invariant 1: append_forecast must be additive-only. No public API in this
    module should expose an update/delete path."""
    from edgeledger import forecast

    log_module = forecast.log
    forbidden = {"update_forecast", "delete_forecast", "update_row", "delete_row"}
    exported = set(dir(log_module))
    assert not (forbidden & exported), f"found forbidden mutation API: {forbidden & exported}"


def test_seq_is_gapless_and_monotonic(tmp_path):
    """Invariant 5: appending N rows produces seq 0..N-1 with no gaps."""
    from edgeledger.forecast.log import append_forecast, next_seq

    data_dir = tmp_path / "forecast_log"
    prev_hash = "genesis"
    for i in range(5):
        seq = next_seq(data_dir)
        assert seq == i, f"expected gapless seq {i}, got {seq}"
        row = _make_row(prev_row_hash=prev_hash, seq=seq)
        append_forecast(row, data_dir)
        prev_hash = row.row_hash
