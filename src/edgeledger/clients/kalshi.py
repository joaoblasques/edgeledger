"""Kalshi API client.

Unauthenticated endpoints are implemented. The orderbook endpoint needs an RSA-PSS
signature over `timestamp_ms + METHOD + path`, and is deliberately left raising until a
key pair exists — see `get_orderbook`.

The gotcha this module exists to encode: **settled markets vanish from `/markets`**. They
move to `/historical/markets`. Poll both, or resolutions silently disappear and the log
quietly stops learning outcomes.
"""

from __future__ import annotations

import logging
from typing import Any

from edgeledger.clients.base import Captured, TokenBucket, VenueClient
from edgeledger.config.settings import (
    UNCONFIRMED_RATE_LIMIT_PER_MIN,
    Settings,
    get_settings,
    get_venues,
)

logger = logging.getLogger(__name__)

# Kalshi caps page size at 1000 for the cursor-paginated collections.
MAX_PAGE_LIMIT = 1000


class KalshiClient(VenueClient):
    """Kalshi trade-api v2. Read-only: there is no order-placement code here, by design."""

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        rate_limiter: TokenBucket | None = None,
        **kwargs: Any,
    ) -> None:
        venue = get_venues().kalshi
        self._settings = settings or get_settings()
        # rate_limit_per_min is null in venues.yaml until confirmed against live docs.
        # Fall back low rather than guessing high — a ban costs the dataset.
        rate = venue.rate_limit_per_min or UNCONFIRMED_RATE_LIMIT_PER_MIN
        super().__init__(
            venue.base_url,
            rate_limiter or TokenBucket(rate_per_min=rate),
            **kwargs,
        )

    # --- unauthenticated ---------------------------------------------------------------

    async def list_markets(self, status: str = "open", **filters: Any) -> Captured:
        """GET /markets. `status` is one of open|closed|settled per Kalshi's docs.

        Note that `settled` here is not a substitute for `/historical/markets` — see
        `list_historical_markets`.
        """
        return await self.get("/markets", params={"status": status, **filters})

    async def get_market(self, ticker: str) -> Captured:
        return await self.get(f"/markets/{ticker}")

    async def get_event(self, event_ticker: str) -> Captured:
        return await self.get(f"/events/{event_ticker}")

    async def get_series(self, series_ticker: str) -> Captured:
        return await self.get(f"/series/{series_ticker}")

    async def list_trades(self, cursor: str | None = None, limit: int = MAX_PAGE_LIMIT) -> Captured:
        """GET /markets/trades, one page. Cursor pagination — see `iter_trades`."""
        params: dict[str, Any] = {"limit": min(limit, MAX_PAGE_LIMIT)}
        if cursor:
            params["cursor"] = cursor
        return await self.get("/markets/trades", params=params)

    async def list_historical_markets(self, **filters: Any) -> Captured:
        """GET /historical/markets — where settled markets go after leaving /markets.

        Polling only /markets loses every resolution. This endpoint is how outcomes are
        recovered, and why the ingestion DAG must hit both.
        """
        return await self.get("/historical/markets", params=filters)

    async def iter_trades(self, limit: int = MAX_PAGE_LIMIT, max_pages: int | None = None):
        """Yield successive `Captured` trade pages until the cursor is exhausted.

        Each page keeps its own capture stamp — a paginated crawl spans real time, and
        collapsing it to one timestamp would misdate most of the rows.
        """
        cursor: str | None = None
        pages = 0
        seen: set[str] = set()

        while True:
            page = await self.list_trades(cursor=cursor, limit=limit)
            yield page
            pages += 1

            cursor = (page.payload or {}).get("cursor") or None
            if not cursor:
                return
            # Kalshi has been observed returning a self-referential cursor at the tail;
            # without this the crawl spins forever re-fetching one page.
            if cursor in seen:
                logger.warning("kalshi cursor repeated, stopping", extra={"cursor": cursor})
                return
            seen.add(cursor)
            if max_pages is not None and pages >= max_pages:
                return

    # --- authenticated -----------------------------------------------------------------

    def _auth_headers(self, method: str, path: str) -> dict[str, str]:
        """Kalshi signs every authenticated request; unauthenticated ones send no headers.

        Only the orderbook endpoint needs this today, so rather than sign everything we
        return empty headers unless credentials exist. `get_orderbook` is the one caller
        that demands them up front.
        """
        if not self._settings.kalshi_authenticated:
            return {}
        raise NotImplementedError(
            "Kalshi RSA-PSS request signing is not implemented yet — needs a key pair to "
            "develop against. See get_orderbook()."
        )

    async def get_orderbook(self, ticker: str, depth: int | None = None) -> Captured:
        """GET /markets/{ticker}/orderbook — AUTH REQUIRED.

        Not yet usable: implementing RSA-PSS signing without a key pair to verify against
        would mean shipping untested crypto, which is worse than an honest failure. The
        credential check runs first so the error names the real blocker.
        """
        self._settings.require_kalshi_credentials()
        raise NotImplementedError(
            "Kalshi orderbook access needs RSA-PSS request signing (KALSHI-ACCESS-KEY / "
            "-SIGNATURE / -TIMESTAMP headers), implemented once a key pair exists."
        )
