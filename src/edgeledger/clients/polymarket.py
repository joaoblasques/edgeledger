"""Polymarket API client (Gamma + CLOB + Data services).

Three hosts, three purposes, all unauthenticated for reads:
  Gamma  https://gamma-api.polymarket.com    discover events/markets, metadata (~60 req/min)
  CLOB   https://clob.polymarket.com         live market state, depth (~100 req/min read)
  Data   https://data-api.polymarket.com     /trades, market activity

Polymarket is this project's **depth venue** (ADR 0002): Kalshi's orderbook endpoint needs
an account that cannot be obtained from Portugal, while Polymarket serves full depth —
typically dozens of levels a side — with no auth at all.

Venue quirks encoded below:
  * Cloudflare 403s requests with a default or absent User-Agent. We always send one.
  * Gamma returns `outcomes`, `outcomePrices`, and `clobTokenIds` as JSON-encoded
    *strings*, not arrays.
  * Multi-outcome markets are bundles of linked binaries — one event, N markets, each with
    its own conditionId and token pair. Never collapse an event into a single row or the
    outcome probabilities won't sum to 1.
  * Some markets ship with an empty conditionId / no tokens (not yet deployed). They are
    unusable for depth and are filtered rather than fetched.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from edgeledger.clients.base import Captured, TokenBucket, VenueClient
from edgeledger.config.settings import get_venues

logger = logging.getLogger(__name__)

USER_AGENT = "edgeledger/0.1 (research; https://github.com/joaoblasques/edgeledger)"

# Gamma caps page size at 500.
MAX_PAGE_LIMIT = 500


def _json_field(raw: Any) -> Any:
    """Decode Gamma's JSON-in-a-string fields, tolerating already-decoded values."""
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return raw
    return raw


def parse_gamma_market(market: dict[str, Any]) -> dict[str, Any]:
    """Normalise one Gamma market: decode the stringified JSON fields.

    Returns a shallow copy. The caller keeps the verbatim payload for bronze — bronze
    stores raw and never transforms on write.
    """
    parsed = dict(market)
    for field in ("outcomes", "outcomePrices", "clobTokenIds"):
        if field in parsed:
            parsed[field] = _json_field(parsed[field])
    return parsed


def has_book(market: dict[str, Any]) -> bool:
    """True if this market currently has a fetchable orderbook.

    Three conditions, all required. Verified against the live API:
      * a deployed conditionId and token pair — undeployed markets have neither;
      * `acceptingOrders` — the CLOB returns 404 for a market that has stopped accepting
        orders, even when it is still flagged active;
      * not `closed`.

    `enableOrderBook` is deliberately NOT used: it stays true on closed markets, so
    trusting it produces a stream of 404s.
    """
    parsed = market if isinstance(market.get("clobTokenIds"), list) else parse_gamma_market(market)
    if not parsed.get("conditionId") or not (parsed.get("clobTokenIds") or []):
        return False
    return bool(parsed.get("acceptingOrders")) and not parsed.get("closed")


def tradeable_markets(event: dict[str, Any]) -> list[dict[str, Any]]:
    """Return an event's markets that currently have a fetchable book.

    A multi-outcome event is N linked binaries, each modelled as its own row — never
    collapsed into one, or the probabilities won't sum to 1. An event can be open while
    individual markets inside it are already closed, so each is checked independently.
    """
    return [m for m in (parse_gamma_market(x) for x in event.get("markets", [])) if has_book(m)]


def deployed_markets(event: dict[str, Any]) -> list[dict[str, Any]]:
    """Every market in the event with a deployed token pair, tradeable or not.

    Resolution polling needs closed markets, which `tradeable_markets` excludes.
    """
    out = []
    for market in event.get("markets", []):
        parsed = parse_gamma_market(market)
        if parsed.get("conditionId") and (parsed.get("clobTokenIds") or []):
            out.append(parsed)
    return out


# Resolved markets settle to ~1/~0, but Gamma reports floats: a real "no" comes back as
# 0.9999989889179474 for the No leg, not 1. Verified against live closed markets.
_RESOLUTION_TOLERANCE = 1e-4


def resolved_outcome(market: dict[str, Any]) -> str | None:
    """Map a Gamma market to yes|no|invalid, or None if the outcome can't be determined.

    Polymarket encodes the outcome in `outcomePrices`: ~["1","0"] is yes, ~["0","1"] is no.

    Three ways this returns None rather than guessing:
      * the market is still open;
      * UMA has not resolved it yet (a market can be `closed` before resolution, so
        treating `closed` alone as resolved would record outcomes that don't exist);
      * Gamma reports ["0","0"] — common on older markets, and it means "no price
        information", not "void". Only a genuine resolution to neither side is `invalid`.
    """
    if not market.get("closed"):
        return None
    status = market.get("umaResolutionStatus")
    if status is not None and status != "resolved":
        return None

    prices = _json_field(market.get("outcomePrices"))
    if not isinstance(prices, list) or len(prices) < 2:
        return None
    try:
        yes, no = float(prices[0]), float(prices[1])
    except (TypeError, ValueError):
        return None

    if abs(yes - 1.0) < _RESOLUTION_TOLERANCE and abs(no) < _RESOLUTION_TOLERANCE:
        return "yes"
    if abs(yes) < _RESOLUTION_TOLERANCE and abs(no - 1.0) < _RESOLUTION_TOLERANCE:
        return "no"
    # Both legs at zero: Gamma has no price info for this market. Unknowable here, and
    # NOT the same as a void resolution — the caller must look elsewhere.
    if abs(yes) < _RESOLUTION_TOLERANCE and abs(no) < _RESOLUTION_TOLERANCE:
        return None
    # Genuinely resolved, but to neither clean side — a void/invalid settlement.
    return "invalid"


class PolymarketClient(VenueClient):
    """Polymarket reads across the gamma / clob / data hosts.

    `VenueClient` is single-base-url, so gamma is the base and the other hosts are reached
    by absolute URL (httpx honours an absolute URL over the client base). Each host gets
    its own token bucket, because their rate limits differ.
    """

    def __init__(
        self,
        *,
        rate_limiter: TokenBucket | None = None,
        clob_rate_limiter: TokenBucket | None = None,
        **kwargs: Any,
    ) -> None:
        venue = get_venues().polymarket
        self._clob_base = venue.clob_base_url.rstrip("/")
        self._data_base = venue.data_base_url.rstrip("/")
        super().__init__(
            venue.gamma_base_url,
            rate_limiter or TokenBucket(rate_per_min=venue.gamma_rate_limit_per_min),
            **kwargs,
        )
        # CLOB has its own limit; sharing gamma's bucket would throttle the wrong host.
        self._clob_limiter = clob_rate_limiter or TokenBucket(
            rate_per_min=venue.clob_rate_limit_per_min
        )

    def _auth_headers(self, method: str, path: str) -> dict[str, str]:
        """Reads need no auth. The User-Agent is mandatory — Cloudflare 403s without it."""
        return {"User-Agent": USER_AGENT}

    # --- gamma: events, markets, resolutions --------------------------------------------

    async def list_events(
        self, *, closed: bool = False, limit: int = MAX_PAGE_LIMIT, offset: int = 0, **filters: Any
    ) -> Captured:
        """GET /events — the natural unit for multi-outcome bundles."""
        return await self.get(
            "/events",
            params={
                "closed": str(closed).lower(),
                "limit": min(limit, MAX_PAGE_LIMIT),
                "offset": offset,
                **filters,
            },
        )

    async def list_markets(
        self, *, closed: bool = False, limit: int = MAX_PAGE_LIMIT, offset: int = 0, **filters: Any
    ) -> Captured:
        """GET /markets. `closed=True` is how resolved markets are found."""
        return await self.get(
            "/markets",
            params={
                "closed": str(closed).lower(),
                "limit": min(limit, MAX_PAGE_LIMIT),
                "offset": offset,
                **filters,
            },
        )

    async def get_market(self, condition_id: str) -> Captured:
        return await self.get("/markets", params={"condition_ids": condition_id})

    async def iter_markets(
        self, *, closed: bool = False, limit: int = MAX_PAGE_LIMIT, max_pages: int | None = None
    ):
        """Yield successive market pages via offset pagination until a short page.

        Each page keeps its own capture stamp — a crawl spans real time, and one stamp for
        all pages would misdate most of the rows.
        """
        offset, pages = 0, 0
        while True:
            page = await self.list_markets(closed=closed, limit=limit, offset=offset)
            yield page
            pages += 1

            rows = page.payload if isinstance(page.payload, list) else []
            # A page shorter than the limit is the last one; Gamma has no cursor.
            if len(rows) < limit:
                return
            if max_pages is not None and pages >= max_pages:
                return
            offset += limit

    # --- clob: depth --------------------------------------------------------------------

    async def get_book(self, token_id: str) -> Captured:
        """GET /book — full orderbook depth for one outcome token.

        The project's depth source. The venue's own `timestamp` stays inside the payload
        and is never reconciled with our capture_ts_utc (invariant 8).
        """
        return await self._get_on(
            self._clob_base, "/book", self._clob_limiter, params={"token_id": token_id}
        )

    async def get_midpoint(self, token_id: str) -> Captured:
        return await self._get_on(
            self._clob_base, "/midpoint", self._clob_limiter, params={"token_id": token_id}
        )

    async def get_prices_history(
        self, token_id: str, *, interval: str = "1d", fidelity: int = 60
    ) -> Captured:
        return await self._get_on(
            self._clob_base,
            "/prices-history",
            self._clob_limiter,
            params={"market": token_id, "interval": interval, "fidelity": fidelity},
        )

    # --- data: trades -------------------------------------------------------------------

    async def list_trades(
        self, *, condition_id: str | None = None, limit: int = 100, offset: int = 0
    ) -> Captured:
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if condition_id:
            params["market"] = condition_id
        return await self._get_on(self._data_base, "/trades", self._clob_limiter, params=params)

    # --- internals ----------------------------------------------------------------------

    async def _get_on(self, base: str, path: str, limiter: TokenBucket, **kwargs: Any) -> Captured:
        """GET against a non-default host, using that host's own rate limiter.

        Swaps the limiter for the duration of the call so the inherited retry, backoff and
        capture-stamping logic in `VenueClient.get` is reused verbatim rather than forked.
        """
        # ponytail: swap-and-restore beats duplicating get()'s retry loop per host. Not
        # safe across *concurrent* calls on ONE client instance — give each crawl its own
        # client, or split into per-host clients if that ever bites.
        original = self._limiter
        self._limiter = limiter
        try:
            return await self.get(f"{base}{path}", **kwargs)
        finally:
            self._limiter = original
