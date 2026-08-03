"""Ingestion routines shared by the DAGs.

The logic lives here rather than inside the DAG files so it is unit-testable without an
Airflow scheduler. The `dags/*.py` modules stay thin: schedule, task graph, and calls into
this module.

Every function takes an explicit `run_id` and `data_dir` and is idempotent through
`bronze.writers.write_rows` — re-running a task replaces that run's own partition and
touches nothing else.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import httpx

from edgeledger.bronze.schemas import (
    Resolution,
    VenueMarketSnapshot,
    VenueOrderbookSnapshot,
    VenueTrade,
)
from edgeledger.bronze.writers import write_rows
from edgeledger.clients.kalshi import KalshiClient
from edgeledger.clients.polymarket import (
    PolymarketClient,
    parse_gamma_market,
    resolved_outcome,
    tradeable_markets,
)

logger = logging.getLogger(__name__)

# Depth is fetched for a bounded set of markets per run: books are the most expensive call
# and the least useful on illiquid markets.
DEFAULT_BOOK_LIMIT = 25


def _to_decimal(value: Any) -> Decimal | None:
    """Parse a venue-supplied number without letting a bad value kill the run."""
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _epoch_to_utc(value: Any) -> datetime | None:
    """Venue epoch timestamps arrive in seconds or milliseconds, as ints or strings."""
    if value is None:
        return None
    try:
        raw = float(value)
    except (TypeError, ValueError):
        return None
    if raw > 1e11:  # milliseconds
        raw /= 1000.0
    try:
        return datetime.fromtimestamp(raw, tz=UTC)
    except (OSError, OverflowError, ValueError):
        return None


# --- Polymarket ------------------------------------------------------------------------


async def ingest_polymarket_markets(
    data_dir: Path, *, run_id: str, max_pages: int = 4
) -> list[dict[str, Any]]:
    """Snapshot open Polymarket markets to bronze. Returns the parsed markets.

    The return value feeds the book fetch in the same DAG run, so discovery is not
    repeated.
    """
    rows: list[VenueMarketSnapshot] = []
    markets: list[dict[str, Any]] = []

    async with PolymarketClient() as client:
        pages = 0
        async for page in client.iter_markets(closed=False, limit=100, max_pages=max_pages):
            pages += 1
            for raw in page.payload if isinstance(page.payload, list) else []:
                parsed = parse_gamma_market(raw)
                condition_id = parsed.get("conditionId")
                if not condition_id:
                    continue
                markets.append(parsed)
                rows.append(
                    VenueMarketSnapshot(
                        capture_ts_utc=page.capture_ts_utc,
                        run_id=run_id,
                        venue="polymarket",
                        venue_market_id=condition_id,
                        payload=json.dumps(raw, separators=(",", ":")),
                        ingest_date=page.capture_ts_utc.date(),
                    )
                )

    write_rows(rows, data_dir, run_id=run_id)
    logger.info("polymarket markets ingested", extra={"rows": len(rows), "pages": pages})
    return markets


async def ingest_polymarket_books(
    markets: list[dict[str, Any]], data_dir: Path, *, run_id: str, limit: int = DEFAULT_BOOK_LIMIT
) -> int:
    """Fetch orderbook depth for the most liquid tradeable markets.

    Polymarket is the depth venue (ADR-0002). Markets that aren't accepting orders have no
    book and are filtered out before any request is made — fetching them just yields 404s.
    """
    tradeable = [m for m in markets if tradeable_markets({"markets": [m]})]
    tradeable.sort(key=lambda m: float(m.get("volumeNum") or m.get("volume") or 0), reverse=True)
    selected = tradeable[:limit]

    rows: list[VenueOrderbookSnapshot] = []
    async with PolymarketClient() as client:
        for market in selected:
            tokens = market.get("clobTokenIds") or []
            outcomes = market.get("outcomes") or []
            for index, token in enumerate(tokens[:2]):
                side = "yes" if index == 0 else "no"
                if index < len(outcomes) and isinstance(outcomes[index], str):
                    side = "yes" if outcomes[index].lower() == "yes" else "no"
                try:
                    book = await client.get_book(str(token))
                except (httpx.HTTPStatusError, httpx.RequestError):
                    # One dead token must not abort the whole run; the market may have
                    # halted between discovery and this call (404 once it stops accepting
                    # orders).
                    logger.warning(
                        "book fetch failed", extra={"token": str(token)[:24]}, exc_info=True
                    )
                    continue
                payload = book.payload or {}
                rows.append(
                    VenueOrderbookSnapshot(
                        capture_ts_utc=book.capture_ts_utc,
                        venue="polymarket",
                        venue_market_id=str(market.get("conditionId")),
                        outcome_side=side,
                        bids=json.dumps(payload.get("bids", []), separators=(",", ":")),
                        asks=json.dumps(payload.get("asks", []), separators=(",", ":")),
                        payload=json.dumps(payload, separators=(",", ":")),
                        ingest_date=book.capture_ts_utc.date(),
                    )
                )

    write_rows(rows, data_dir, run_id=run_id)
    logger.info("polymarket books ingested", extra={"rows": len(rows), "markets": len(selected)})
    return len(rows)


async def ingest_polymarket_trades(
    markets: list[dict[str, Any]], data_dir: Path, *, run_id: str, limit: int = DEFAULT_BOOK_LIMIT
) -> int:
    """Fetch recent trade prints for the selected markets."""
    rows: list[VenueTrade] = []

    async with PolymarketClient() as client:
        for market in markets[:limit]:
            condition_id = market.get("conditionId")
            if not condition_id:
                continue
            try:
                page = await client.list_trades(condition_id=str(condition_id), limit=100)
            except (httpx.HTTPStatusError, httpx.RequestError):
                logger.warning(
                    "trade fetch failed", extra={"market": str(condition_id)[:24]}, exc_info=True
                )
                continue
            for raw in page.payload if isinstance(page.payload, list) else []:
                trade_ts = _epoch_to_utc(raw.get("timestamp"))
                price = _to_decimal(raw.get("price"))
                size = _to_decimal(raw.get("size"))
                trade_id = raw.get("transactionHash") or raw.get("id")
                if not (trade_ts and price is not None and size is not None and trade_id):
                    continue
                rows.append(
                    VenueTrade(
                        capture_ts_utc=page.capture_ts_utc,
                        venue="polymarket",
                        venue_market_id=str(condition_id),
                        venue_trade_id=str(trade_id),
                        trade_ts_utc=trade_ts,
                        price=price,
                        size=size,
                        payload=json.dumps(raw, separators=(",", ":")),
                        ingest_date=page.capture_ts_utc.date(),
                    )
                )

    write_rows(rows, data_dir, run_id=run_id)
    logger.info("polymarket trades ingested", extra={"rows": len(rows)})
    return len(rows)


# --- Kalshi ----------------------------------------------------------------------------


async def ingest_kalshi_markets(data_dir: Path, *, run_id: str) -> list[dict[str, Any]]:
    """Snapshot open Kalshi markets to bronze.

    Unauthenticated only — Kalshi supplies no depth here (ADR-0002).
    """
    rows: list[VenueMarketSnapshot] = []
    markets: list[dict[str, Any]] = []

    async with KalshiClient() as client:
        page = await client.list_markets(status="open", limit=200)
        payload = page.payload or {}
        for raw in payload.get("markets", []):
            ticker = raw.get("ticker")
            if not ticker:
                continue
            markets.append(raw)
            rows.append(
                VenueMarketSnapshot(
                    capture_ts_utc=page.capture_ts_utc,
                    run_id=run_id,
                    venue="kalshi",
                    venue_market_id=str(ticker),
                    payload=json.dumps(raw, separators=(",", ":")),
                    ingest_date=page.capture_ts_utc.date(),
                )
            )

    write_rows(rows, data_dir, run_id=run_id)
    logger.info("kalshi markets ingested", extra={"rows": len(rows)})
    return markets


async def ingest_kalshi_trades(data_dir: Path, *, run_id: str, max_pages: int = 3) -> int:
    """Fetch recent Kalshi trade prints across all markets."""
    rows: list[VenueTrade] = []

    async with KalshiClient() as client:
        async for page in client.iter_trades(limit=1000, max_pages=max_pages):
            for raw in (page.payload or {}).get("trades", []):
                trade_ts = _epoch_to_utc(raw.get("created_time") or raw.get("ts"))
                price = _to_decimal(raw.get("yes_price"))
                size = _to_decimal(raw.get("count"))
                trade_id = raw.get("trade_id")
                ticker = raw.get("ticker")
                if not (trade_ts and price is not None and size is not None and trade_id):
                    continue
                rows.append(
                    VenueTrade(
                        capture_ts_utc=page.capture_ts_utc,
                        venue="kalshi",
                        venue_market_id=str(ticker),
                        venue_trade_id=str(trade_id),
                        trade_ts_utc=trade_ts,
                        # Kalshi quotes cents; bronze stores probability units.
                        price=price / Decimal(100),
                        size=size,
                        payload=json.dumps(raw, separators=(",", ":")),
                        ingest_date=page.capture_ts_utc.date(),
                    )
                )

    write_rows(rows, data_dir, run_id=run_id)
    logger.info("kalshi trades ingested", extra={"rows": len(rows)})
    return len(rows)


# --- resolutions ------------------------------------------------------------------------


async def ingest_polymarket_resolutions(data_dir: Path, *, run_id: str, pages: int = 2) -> int:
    """Poll closed Polymarket markets and record settled outcomes.

    `resolved_outcome` returns None when the outcome cannot be determined — closed but not
    yet resolved by UMA, or no price information at all. Those are skipped rather than
    guessed: a fabricated outcome in the log is worse than a missing one.
    """
    rows: list[Resolution] = []

    async with PolymarketClient() as client:
        async for page in client.iter_markets(closed=True, limit=100, max_pages=pages):
            for raw in page.payload if isinstance(page.payload, list) else []:
                parsed = parse_gamma_market(raw)
                outcome = resolved_outcome(parsed)
                condition_id = parsed.get("conditionId")
                if not outcome or not condition_id:
                    continue
                resolution_ts = (
                    _epoch_to_utc(parsed.get("closedTime"))
                    or _parse_iso(parsed.get("endDate"))
                    or page.capture_ts_utc
                )
                rows.append(
                    Resolution(
                        capture_ts_utc=page.capture_ts_utc,
                        venue="polymarket",
                        venue_market_id=str(condition_id),
                        resolved_outcome=outcome,
                        resolution_ts_utc=resolution_ts,
                        payload=json.dumps(raw, separators=(",", ":")),
                    )
                )

    write_rows(rows, data_dir, run_id=run_id)
    logger.info("polymarket resolutions ingested", extra={"rows": len(rows)})
    return len(rows)


async def ingest_kalshi_resolutions(data_dir: Path, *, run_id: str) -> int:
    """Poll settled Kalshi markets, including `/historical/markets`.

    Settled markets vanish from `/markets`, so polling only that endpoint loses
    resolutions silently. Both are polled here.
    """
    rows: list[Resolution] = []
    seen: set[str] = set()

    async with KalshiClient() as client:
        pages = [
            await client.list_markets(status="settled", limit=200),
            await client.list_historical_markets(limit=200),
        ]
        for page in pages:
            for raw in (page.payload or {}).get("markets", []):
                ticker = raw.get("ticker")
                result = (raw.get("result") or "").lower()
                if not ticker or ticker in seen:
                    continue
                if result not in ("yes", "no"):
                    continue
                seen.add(str(ticker))
                rows.append(
                    Resolution(
                        capture_ts_utc=page.capture_ts_utc,
                        venue="kalshi",
                        venue_market_id=str(ticker),
                        resolved_outcome=result,
                        resolution_ts_utc=(
                            _parse_iso(raw.get("close_time")) or page.capture_ts_utc
                        ),
                        payload=json.dumps(raw, separators=(",", ":")),
                    )
                )

    write_rows(rows, data_dir, run_id=run_id)
    logger.info("kalshi resolutions ingested", extra={"rows": len(rows)})
    return len(rows)


def _parse_iso(value: Any) -> datetime | None:
    """Parse an ISO-8601 venue timestamp into aware UTC, or None."""
    if not isinstance(value, str) or not value:
        return None
    # Python's fromisoformat accepts "Z" only from 3.11 on some paths; normalise first.
    text = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    # A venue timestamp with no offset is documented as UTC; make that explicit.
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def recent_partition_date(days_back: int = 2) -> date:
    """The oldest partition date a run should scan. Keeps feature builds bounded."""
    return (datetime.now(UTC) - timedelta(days=days_back)).date()
