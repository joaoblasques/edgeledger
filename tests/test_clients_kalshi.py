"""Tests for the Kalshi client and config loading.

The load-bearing test here is the settled-markets one: polling only /markets loses every
resolution, which would make the forecast log quietly stop learning outcomes.
"""

from __future__ import annotations

import asyncio

import httpx
import pytest

from edgeledger.clients.base import TokenBucket
from edgeledger.clients.kalshi import KalshiClient
from edgeledger.config.settings import Settings, get_venues


def _kalshi(handler, settings: Settings | None = None) -> KalshiClient:
    http = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="https://kalshi.test"
    )
    return KalshiClient(
        settings=settings or Settings(_env_file=None),
        rate_limiter=TokenBucket(rate_per_min=600_000),
        client=http,
    )


# --- the settled-markets trap --------------------------------------------------------


def test_settled_markets_come_from_historical_endpoint():
    """A market that has settled is gone from /markets and must be found in
    /historical/markets. Polling only the former silently loses resolutions."""
    paths = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        if request.url.path == "/markets":
            return httpx.Response(200, json={"markets": []})  # settled one has vanished
        if request.url.path == "/historical/markets":
            return httpx.Response(200, json={"markets": [{"ticker": "T-1", "result": "yes"}]})
        return httpx.Response(404, json={})

    async def main():
        c = _kalshi(handler)
        open_markets = await c.list_markets(status="open")
        historical = await c.list_historical_markets(ticker="T-1")
        return open_markets, historical

    open_markets, historical = asyncio.run(main())

    assert open_markets.payload["markets"] == []
    assert historical.payload["markets"][0]["result"] == "yes"
    assert "/historical/markets" in paths


# --- pagination ----------------------------------------------------------------------


def test_iter_trades_follows_cursor_to_exhaustion():
    pages = [
        {"trades": [{"trade_id": "a"}], "cursor": "c1"},
        {"trades": [{"trade_id": "b"}], "cursor": "c2"},
        {"trades": [{"trade_id": "c"}], "cursor": ""},  # empty cursor = last page
    ]
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.params.get("cursor"))
        return httpx.Response(200, json=pages[len(calls) - 1])

    async def main():
        return [p async for p in _kalshi(handler).iter_trades()]

    got = asyncio.run(main())

    assert len(got) == 3
    assert [t.payload["trades"][0]["trade_id"] for t in got] == ["a", "b", "c"]
    assert calls == [None, "c1", "c2"]


def test_iter_trades_stops_on_repeated_cursor():
    """A self-referential cursor must not spin the crawl forever."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"trades": [], "cursor": "same"})

    async def main():
        return [p async for p in _kalshi(handler).iter_trades()]

    assert len(asyncio.run(main())) == 2, "second page repeats the cursor, so we stop"


def test_each_page_keeps_its_own_capture_stamp():
    """A paginated crawl spans real time; one stamp for all pages would misdate rows."""
    pages = [
        {"trades": [], "cursor": "c1"},
        {"trades": [], "cursor": ""},
    ]
    calls = []

    async def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        await asyncio.sleep(0.05)
        return httpx.Response(200, json=pages[len(calls) - 1])

    async def main():
        return [p async for p in _kalshi(handler).iter_trades()]

    got = asyncio.run(main())
    assert got[0].capture_ts_utc < got[1].capture_ts_utc


# --- auth gating ---------------------------------------------------------------------


def test_orderbook_without_credentials_names_the_blocker():
    """Unauthenticated orderbook access fails on the missing key pair, not on signing."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={})

    with pytest.raises(RuntimeError, match="KALSHI_ACCESS_KEY"):
        asyncio.run(_kalshi(handler).get_orderbook("T-1"))


def test_unauthenticated_endpoints_send_no_auth_headers():
    """Without credentials the client must still work — most endpoints need no auth."""
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(request.headers)
        return httpx.Response(200, json={"markets": []})

    asyncio.run(_kalshi(handler).list_markets())

    assert not any(k.lower().startswith("kalshi-access") for k in seen)


# --- config --------------------------------------------------------------------------


def test_venues_yaml_parses_with_unconfirmed_rate_limit_as_none():
    v = get_venues()
    assert v.kalshi.base_url.startswith("https://")
    assert v.kalshi.rate_limit_per_min is None, "still a TODO in venues.yaml, must stay honest"
    assert v.kalshi.orderbook_requires_auth is True
    assert v.polymarket.gamma_rate_limit_per_min == 60


def test_blank_env_values_are_treated_as_unset():
    """.env.example ships KALSHI_ACCESS_KEY= empty; blank must not count as a credential."""
    s = Settings(_env_file=None, kalshi_access_key="  ", kalshi_private_key_path=None)
    assert s.kalshi_authenticated is False
