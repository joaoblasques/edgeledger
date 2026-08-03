"""Naive baseline models and the point-in-time feature builder (month-01 spec §6).

Two deliberately trivial models: the control that validates the pipeline end to end, and
the floor every later model must beat.

`build_feature_vector` is the leakage firewall (invariant 3). It is the single place
bronze rows are selected for a forecast, and therefore the single place a future-dated row
could slip in. It filters on `capture_ts_utc <= feature_cutoff_ts_utc` and nothing else —
no venue timestamp, no "close enough" tolerance. `tests/test_point_in_time.py` asserts it.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Protocol

logger = logging.getLogger(__name__)

MARKET_MIRROR_VERSION = "1.0.0"
BASE_RATE_VERSION = "1.0.0"


class _HasCaptureTs(Protocol):
    """Anything with a capture stamp — the bronze row types all satisfy this."""

    capture_ts_utc: datetime


@dataclass(frozen=True, slots=True)
class FeatureVector:
    """Features plus the exact rows they came from.

    `source_snapshots` is not bookkeeping — it is the evidence that the cutoff was
    respected, and it is what the point-in-time test inspects.
    """

    feature_cutoff_ts_utc: datetime
    source_snapshots: tuple[_HasCaptureTs, ...]
    features: dict[str, float]

    def to_json(self) -> str:
        """Serialise for `ForecastLogRow.feature_vector`."""
        return json.dumps(self.features, sort_keys=True, separators=(",", ":"))


def build_feature_vector(
    snapshots: list[_HasCaptureTs],
    feature_cutoff_ts_utc: datetime,
    features: dict[str, float] | None = None,
) -> FeatureVector:
    """Select the bronze rows a forecast may use, and refuse everything after the cutoff.

    A row captured even one second after `feature_cutoff_ts_utc` is excluded. This is
    strict by design: any tolerance here is a leak, and a leak is indistinguishable from
    a model that appears to work.

    Rows are excluded silently in the return value but counted in the log, so a
    misconfigured cutoff shows up as an anomaly rather than passing unnoticed.
    """
    kept = tuple(s for s in snapshots if s.capture_ts_utc <= feature_cutoff_ts_utc)
    dropped = len(snapshots) - len(kept)
    if dropped:
        logger.info(
            "feature builder excluded post-cutoff rows",
            extra={
                "cutoff": feature_cutoff_ts_utc.isoformat(),
                "kept": len(kept),
                "dropped": dropped,
            },
        )
    return FeatureVector(
        feature_cutoff_ts_utc=feature_cutoff_ts_utc,
        source_snapshots=kept,
        features=features or {},
    )


def market_mirror(mkt_yes_mid: Decimal) -> Decimal:
    """`p_hat = mkt_yes_mid`. Zero edge by construction.

    Not a model — a canary. If its Brier score is not statistically indistinguishable
    from `brier_market`, the pipeline is broken, not the model. That makes it the
    cheapest possible end-to-end test of the measurement layer.
    """
    if not Decimal(0) <= mkt_yes_mid <= Decimal(1):
        raise ValueError(f"mkt_yes_mid must be a probability in [0, 1], got {mkt_yes_mid}")
    return mkt_yes_mid


def base_rate(outcome_class: str, historical_frequencies: dict[str, Decimal]) -> Decimal:
    """`p_hat` = the historical frequency of this outcome class.

    Genuinely naive and expected to lose to the market. The point is an honest floor:
    a model that cannot beat this has no edge worth reporting.
    """
    try:
        frequency = historical_frequencies[outcome_class]
    except KeyError:
        raise KeyError(
            f"no historical frequency for outcome class {outcome_class!r} — "
            "refusing to guess a prior"
        ) from None
    if not Decimal(0) <= frequency <= Decimal(1):
        raise ValueError(f"frequency for {outcome_class!r} must be in [0, 1], got {frequency}")
    return frequency
