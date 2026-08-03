"""Pydantic mirror of the `forecast_log` DDL (month-01 spec §5).

This is the single source of truth for the shape of a forecast row. Every writer,
reader, and test in this repo constructs or validates a `ForecastLogRow` — never a
bare dict. See CLAUDE.md invariants 1-8; this model encodes invariants 2, 3, 6, 7, 8
at the type level. Invariants 1 (append-only) and 4/5 (hash chain, gapless seq) are
enforced by the writer in `forecast/log.py`, not here.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

OutcomeSide = Literal["yes"]
Venue = Literal["kalshi", "polymarket"]


def _require_utc(value: datetime, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(None):
        raise ValueError(f"{field_name} must be timezone-aware UTC (invariant 7: everything UTC)")
    return value


class ForecastLogRow(BaseModel):
    """One row of `forecast_log`. Immutable once written — see invariant 1."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    # --- identity ---
    forecast_id: UUID  # UUIDv7, time-sortable
    seq: int  # monotonic, gapless (invariant 5) — assigned by the writer, not here
    forecast_ts_utc: datetime  # when written

    # --- provenance ---
    model_name: str
    model_version: str  # semver
    code_git_sha: str
    run_id: str

    # --- market identity ---
    venue: Venue
    venue_market_id: str
    canonical_market_id: str | None = None  # cross-venue link, nullable
    market_question: str
    category: str | None = None
    outcome_side: OutcomeSide  # always forecast 'yes'

    # --- the prediction ---
    p_hat: Decimal  # P(yes)
    p_hat_lo: Decimal | None = None  # 90% interval
    p_hat_hi: Decimal | None = None

    # --- market state AT FORECAST TIME (invariant 2: never backfilled) ---
    mkt_yes_bid: Decimal | None = None
    mkt_yes_ask: Decimal | None = None
    mkt_yes_mid: Decimal | None = None
    mkt_spread: Decimal | None = None
    mkt_depth_1pct: Decimal | None = None  # size within 1c of mid
    mkt_volume_cum: Decimal | None = None
    orderbook_ref: str | None = None  # FK to bronze snapshot

    # --- point-in-time contract (invariant 3: the leakage firewall) ---
    feature_cutoff_ts_utc: datetime
    feature_vector: str  # JSON
    feature_set_version: str

    # --- derived at write time ---
    edge: Decimal | None = None  # p_hat - mkt_yes_mid
    horizon_seconds: int | None = None  # to expected resolution

    # --- intent (not execution — no order-placement path exists in this repo) ---
    intended_stake_units: Decimal | None = None
    sizing_rule: str | None = None

    # --- tamper evidence (invariant 4: hash chain) ---
    row_hash: str
    prev_row_hash: str

    # Supersession: corrections are new rows, never edits (invariant 1).
    supersedes_forecast_id: UUID | None = None

    @field_validator("forecast_ts_utc", "feature_cutoff_ts_utc")
    @classmethod
    def _utc_timestamps(cls, value: datetime, info) -> datetime:
        return _require_utc(value, info.field_name)

    @field_validator("p_hat")
    @classmethod
    def _p_hat_in_unit_interval(cls, value: Decimal) -> Decimal:
        if not (Decimal(0) <= value <= Decimal(1)):
            raise ValueError("p_hat must be in [0, 1]")
        return value

    @field_validator("seq")
    @classmethod
    def _seq_non_negative(cls, value: int) -> int:
        if value < 0:
            raise ValueError("seq must be non-negative")
        return value

    @model_validator(mode="after")
    def _feature_cutoff_not_after_forecast(self) -> ForecastLogRow:
        # Invariant 3: features may never reflect information from after the cutoff,
        # and the cutoff itself may never be later than the forecast's own write time.
        if self.feature_cutoff_ts_utc > self.forecast_ts_utc:
            raise ValueError(
                "feature_cutoff_ts_utc cannot be after forecast_ts_utc "
                "(leakage firewall violation)"
            )
        return self

    @model_validator(mode="after")
    def _interval_bounds_consistent(self) -> ForecastLogRow:
        if self.p_hat_lo is not None and self.p_hat_hi is not None and self.p_hat_lo > self.p_hat_hi:
            raise ValueError("p_hat_lo must be <= p_hat_hi")
        return self
