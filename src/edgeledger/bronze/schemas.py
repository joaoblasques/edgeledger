"""Pydantic models for the four bronze tables (month-01 spec §4, docs/data-model.md).

Bronze is raw. The full venue response is kept verbatim in `payload`; only a few keys are
extracted, and those exist for partitioning and dedupe, not for analysis. Schema drift is a
silver-layer problem — never an ingestion failure, because a rejected row is a permanently
lost observation.

Two invariants are enforced at the type level here:
  * invariant 7 — every timestamp is timezone-aware UTC;
  * invariant 8 — `capture_ts_utc` (ours) and venue timestamps (`trade_ts_utc`,
    `resolution_ts_utc`) are separate fields, never reconciled into one.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator

Venue = Literal["kalshi", "polymarket"]
OutcomeSide = Literal["yes", "no"]
ResolvedOutcome = Literal["yes", "no", "invalid"]


def _require_utc(value: datetime, field_name: str) -> datetime:
    """Same contract as forecast/schema.py::_require_utc — invariant 7, everywhere."""
    if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(None):
        raise ValueError(f"{field_name} must be timezone-aware UTC (invariant 7: everything UTC)")
    return value


class _BronzeRow(BaseModel):
    """Shared base: UTC validation and immutability for every bronze row."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    capture_ts_utc: datetime

    @field_validator("capture_ts_utc", "trade_ts_utc", "resolution_ts_utc", check_fields=False)
    @classmethod
    def _utc_timestamps(cls, value: datetime, info) -> datetime:
        return _require_utc(value, info.field_name)


class VenueMarketSnapshot(_BronzeRow):
    """One market's state as returned by the venue, verbatim."""

    run_id: str
    venue: Venue
    venue_market_id: str  # ticker (Kalshi) | conditionId (Polymarket)
    payload: str  # full JSON, verbatim
    ingest_date: date  # partition key


class VenueOrderbookSnapshot(_BronzeRow):
    """One side's book depth. Polymarket only for now — see ADR-0002."""

    venue: Venue
    venue_market_id: str
    outcome_side: OutcomeSide
    bids: str  # JSON [[price, size], ...]
    asks: str
    payload: str
    ingest_date: date


class VenueTrade(_BronzeRow):
    """A single trade print.

    `trade_ts_utc` is the venue's own clock, `capture_ts_utc` is ours. They sit side by
    side and are never reconciled (invariant 8) — the gap between them is real information
    about ingestion lag, and collapsing them destroys it.
    """

    venue: Venue
    venue_market_id: str
    venue_trade_id: str  # dedupe key
    trade_ts_utc: datetime
    price: Decimal
    size: Decimal
    payload: str
    ingest_date: date


class Resolution(_BronzeRow):
    """A settled outcome. Never joined into forecast_log — only into the scoring view."""

    venue: Venue
    venue_market_id: str
    resolved_outcome: ResolvedOutcome
    resolution_ts_utc: datetime
    payload: str
