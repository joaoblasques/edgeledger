"""Runs the baseline models over tracked markets and appends to the forecast log.

This is what starts the twelve-month clock. Everything it does is constrained by the
invariants, and three of them bite directly here:

  * **invariant 2** — market state is read from the bronze snapshot the forecast is built
    from and embedded in the row. It is never joined in afterwards.
  * **invariant 3** — `feature_cutoff_ts_utc` is chosen first, and only bronze rows
    captured at or before it are visible to the model. `build_feature_vector` enforces it.
  * **invariant 5** — `seq` comes from `next_seq` and rows are appended one at a time, so
    a partial run leaves a shorter chain, never a gapped one.

A market with no usable price is skipped, not defaulted. A forecast of 0.5 "because we had
nothing" would be indistinguishable in the log from a genuine 0.5 belief.
"""

from __future__ import annotations

import json
import logging
import subprocess
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import uuid4

from edgeledger.bronze.schemas import VenueMarketSnapshot
from edgeledger.bronze.writers import read_since
from edgeledger.forecast.baselines import (
    MARKET_MIRROR_VERSION,
    build_feature_vector,
    market_mirror,
)
from edgeledger.forecast.log import append_forecast, next_seq
from edgeledger.forecast.schema import ForecastLogRow

logger = logging.getLogger(__name__)

FEATURE_SET_VERSION = "v1"


def code_git_sha() -> str:
    """The commit the forecast was produced by — provenance, per the schema.

    Falls back to "unknown" rather than raising: a missing SHA must not stop a forecast
    being written, but it must be visible in the row that it was missing.
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        )
    except (subprocess.SubprocessError, OSError):
        return "unknown"
    return result.stdout.strip() or "unknown"


def _mid_from_payload(payload: dict[str, Any]) -> tuple[Decimal | None, Decimal | None, Decimal | None]:
    """Extract (bid, ask, mid) from a Gamma market payload, if present.

    Returns Nones when the market has no usable two-sided price. The caller skips those
    rather than inventing a number.
    """
    def _dec(value: Any) -> Decimal | None:
        if value is None:
            return None
        try:
            return Decimal(str(value))
        except (ArithmeticError, ValueError):
            return None

    bid = _dec(payload.get("bestBid"))
    ask = _dec(payload.get("bestAsk"))
    if bid is not None and ask is not None:
        return bid, ask, (bid + ask) / Decimal(2)

    # Fall back to the last traded price only if there is no book side at all.
    prices = payload.get("outcomePrices")
    if isinstance(prices, str):
        try:
            prices = json.loads(prices)
        except json.JSONDecodeError:
            prices = None
    if isinstance(prices, list) and prices:
        mid = _dec(prices[0])
        if mid is not None and Decimal(0) < mid < Decimal(1):
            return bid, ask, mid
    return bid, ask, None


def _horizon_seconds(payload: dict[str, Any], forecast_ts: datetime) -> int | None:
    """Seconds from now to the market's stated end, or None if it has none.

    Taken from the same snapshot payload the forecast is built from, so it is market state
    at forecast time (invariant 2) — never a later lookup. `endDate` is the venue's own
    field and is treated as a stated intention, not a guarantee: a market can settle early
    or late, which is why scoring still keys off observed resolutions and this is only used
    to bucket a forecast by its expected horizon.

    Returns None rather than a negative number for an already-passed end date: "expected to
    resolve in the past" is not a horizon, and a negative value would silently corrupt any
    average built on this field.
    """
    end = payload.get("endDate")
    if not isinstance(end, str) or not end:
        return None
    text = end[:-1] + "+00:00" if end.endswith("Z") else end
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    seconds = int((parsed - forecast_ts).total_seconds())
    return seconds if seconds > 0 else None


def run_market_mirror(
    data_dir: Path,
    *,
    run_id: str,
    days_back: int = 1,
    limit: int | None = None,
) -> int:
    """Forecast every tracked market with `market_mirror`, appending each to the log.

    Returns the number of forecasts written.

    The cutoff is stamped once, at the start of the run, and every forecast in the run
    shares it. That is deliberate: it makes the point-in-time claim checkable for the
    whole batch against a single timestamp.
    """
    cutoff = datetime.now(UTC)
    git_sha = code_git_sha()

    snapshots = read_since(VenueMarketSnapshot, data_dir, since=cutoff.date())
    if not snapshots and days_back:
        # Nothing captured today yet — widen by one day so an early run still has input.
        snapshots = read_since(
            VenueMarketSnapshot, data_dir, since=(cutoff - timedelta(days=days_back)).date()
        )

    # One forecast per market: the newest snapshot at or before the cutoff wins.
    latest: dict[tuple[str, str], VenueMarketSnapshot] = {}
    for snap in snapshots:
        if snap.capture_ts_utc > cutoff:
            continue
        key = (snap.venue, snap.venue_market_id)
        if key not in latest or snap.capture_ts_utc > latest[key].capture_ts_utc:
            latest[key] = snap

    written = 0
    skipped_no_price = 0

    for (venue, market_id), snap in sorted(latest.items()):
        if limit is not None and written >= limit:
            break

        try:
            payload = json.loads(snap.payload)
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict):
            continue

        bid, ask, mid = _mid_from_payload(payload)
        if mid is None:
            skipped_no_price += 1
            continue

        # The firewall: only this snapshot, and only because it is at or before the cutoff.
        features = build_feature_vector(
            [snap],
            feature_cutoff_ts_utc=cutoff,
            features={"mkt_yes_mid": float(mid)},
        )
        if not features.source_snapshots:
            continue

        p_hat = market_mirror(mid)
        # Bound once: the horizon must be measured from the same instant the row records,
        # not from a second clock read a few microseconds later.
        forecast_ts = datetime.now(UTC)
        row = ForecastLogRow(
            forecast_id=uuid4(),
            seq=next_seq(data_dir),
            forecast_ts_utc=forecast_ts,
            model_name="market_mirror",
            model_version=MARKET_MIRROR_VERSION,
            code_git_sha=git_sha,
            run_id=run_id,
            venue=venue,  # type: ignore[arg-type]
            venue_market_id=market_id,
            market_question=str(payload.get("question") or payload.get("title") or market_id)[:500],
            outcome_side="yes",
            p_hat=p_hat,
            # Invariant 2: market state as it was at forecast time, from this snapshot.
            mkt_yes_bid=bid,
            mkt_yes_ask=ask,
            mkt_yes_mid=mid,
            mkt_spread=(ask - bid) if (bid is not None and ask is not None) else None,
            orderbook_ref=snap.capture_ts_utc.isoformat(),
            feature_cutoff_ts_utc=cutoff,
            feature_vector=features.to_json(),
            feature_set_version=FEATURE_SET_VERSION,
            edge=p_hat - mid,
            horizon_seconds=_horizon_seconds(payload, forecast_ts),
            row_hash="pending",  # filled in by append_forecast
            prev_row_hash="pending",
        )
        append_forecast(row, data_dir)
        written += 1

    logger.info(
        "baseline forecasts appended",
        extra={
            "model": "market_mirror",
            "written": written,
            "skipped_no_price": skipped_no_price,
            "cutoff": cutoff.isoformat(),
            "run_id": run_id,
        },
    )
    return written
