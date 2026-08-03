"""Tests for the Polymarket client.

The load-bearing cases are the venue quirks that silently corrupt data if mishandled:
stringified JSON fields, multi-outcome bundles, and closed-but-not-resolved markets.
"""

from __future__ import annotations

import asyncio

import httpx

from edgeledger.clients.base import TokenBucket
from edgeledger.clients.polymarket import (
    USER_AGENT,
    PolymarketClient,
    deployed_markets,
    has_book,
    parse_gamma_market,
    resolved_outcome,
    tradeable_markets,
)


def _poly(handler) -> PolymarketClient:
    http = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://gamma-api.polymarket.com",
    )
    return PolymarketClient(
        rate_limiter=TokenBucket(rate_per_min=600_000),
        clob_rate_limiter=TokenBucket(rate_per_min=600_000),
        client=http,
    )


# --- Gamma's stringified JSON --------------------------------------------------------


def test_gamma_json_string_fields_are_decoded():
    """Gamma returns outcomes/prices/tokens as JSON *strings*, not arrays."""
    raw = {
        "conditionId": "0xabc",
        "outcomes": '["Yes", "No"]',
        "outcomePrices": '["0.0455", "0.9545"]',
        "clobTokenIds": '["tok-yes", "tok-no"]',
    }
    parsed = parse_gamma_market(raw)

    assert parsed["outcomes"] == ["Yes", "No"]
    assert parsed["outcomePrices"] == ["0.0455", "0.9545"]
    assert parsed["clobTokenIds"] == ["tok-yes", "tok-no"]
    # The input must not be mutated — bronze keeps the verbatim payload.
    assert isinstance(raw["outcomes"], str)


def test_parse_tolerates_already_decoded_fields():
    parsed = parse_gamma_market({"outcomes": ["Yes", "No"], "clobTokenIds": ["a", "b"]})
    assert parsed["outcomes"] == ["Yes", "No"]


# --- multi-outcome bundles -----------------------------------------------------------


def _mkt(cid: str, *, accepting: bool = True, closed: bool = False, tokens: str = '["a","b"]'):
    return {
        "conditionId": cid,
        "clobTokenIds": tokens,
        "acceptingOrders": accepting,
        "closed": closed,
        "enableOrderBook": True,
    }


def test_multi_outcome_event_yields_one_row_per_binary():
    """One event, N linked binaries. Collapsing them into a single row would break
    probability summation — each conditionId is its own market."""
    event = {
        "title": "Kraken IPO by ___ ?",
        "markets": [_mkt("0x1"), _mkt("0x2"), _mkt("0x3")],
    }
    markets = tradeable_markets(event)

    assert len(markets) == 3
    assert [m["conditionId"] for m in markets] == ["0x1", "0x2", "0x3"]
    assert all(len(m["clobTokenIds"]) == 2 for m in markets)


def test_undeployed_markets_are_filtered_out():
    """Some markets ship with an empty conditionId and no tokens — no book to fetch."""
    event = {
        "markets": [
            _mkt("0x1"),
            _mkt("", tokens="null"),
            _mkt("0x3", tokens="[]"),
        ]
    }
    assert [m["conditionId"] for m in tradeable_markets(event)] == ["0x1"]


def test_markets_not_accepting_orders_have_no_book():
    """Verified live: the CLOB 404s a market that has stopped accepting orders, even
    while it is still flagged active with enableOrderBook true."""
    event = {
        "markets": [
            _mkt("0x-open"),
            _mkt("0x-halted", accepting=False),
            _mkt("0x-closed", accepting=False, closed=True),
        ]
    }
    assert [m["conditionId"] for m in tradeable_markets(event)] == ["0x-open"]
    assert has_book(_mkt("0x-halted", accepting=False)) is False


def test_enable_order_book_flag_is_not_trusted():
    """enableOrderBook stays true on closed markets — trusting it yields 404s."""
    closed = _mkt("0x1", accepting=False, closed=True)
    assert closed["enableOrderBook"] is True
    assert has_book(closed) is False


def test_deployed_markets_keeps_closed_ones_for_resolution_polling():
    """Resolution polling needs closed markets, which tradeable_markets excludes."""
    event = {
        "markets": [_mkt("0x-open"), _mkt("0x-closed", accepting=False, closed=True)],
    }
    assert len(deployed_markets(event)) == 2
    assert len(tradeable_markets(event)) == 1


# --- resolution -----------------------------------------------------------------------


def test_resolved_outcome_reads_outcome_prices():
    yes = {"closed": True, "umaResolutionStatus": "resolved", "outcomePrices": '["1","0"]'}
    no = {"closed": True, "umaResolutionStatus": "resolved", "outcomePrices": '["0","1"]'}
    assert resolved_outcome(yes) == "yes"
    assert resolved_outcome(no) == "no"


def test_closed_but_unresolved_is_not_an_outcome():
    """A market can be closed before UMA resolves it. Treating closed as resolved would
    record an outcome that does not exist yet."""
    pending = {
        "closed": True,
        "umaResolutionStatus": "proposed",
        "outcomePrices": '["1","0"]',
    }
    assert resolved_outcome(pending) is None


def test_open_market_has_no_outcome():
    assert resolved_outcome({"closed": False, "outcomePrices": '["0.5","0.5"]'}) is None


def test_ambiguous_resolution_is_invalid_not_yes():
    """A resolved market that didn't settle to a clean 1/0 is void, not a yes."""
    void = {"closed": True, "umaResolutionStatus": "resolved", "outcomePrices": '["0.5","0.5"]'}
    assert resolved_outcome(void) == "invalid"


def test_floating_point_resolution_prices_are_recognised():
    """Live data: a resolved "no" comes back as 0.9999989889 on the No leg, not 1.
    Exact == 1.0 comparison would misreport every one of these as invalid."""
    real_no = {
        "closed": True,
        "outcomePrices": (
            '["0.000001011082052522541417308141468657552",'
            ' "0.9999989889179474774585826918585313"]'
        ),
    }
    assert resolved_outcome(real_no) == "no"

    real_yes = {"closed": True, "outcomePrices": '["0.99999898", "0.00000101"]'}
    assert resolved_outcome(real_yes) == "yes"


def test_zero_zero_prices_are_unknown_not_invalid():
    """Older closed markets report ["0","0"] — that is missing price information, not a
    void resolution. Calling it invalid would fabricate outcomes for the log."""
    no_info = {"closed": True, "outcomePrices": '["0","0"]'}
    assert resolved_outcome(no_info) is None


# --- HTTP behaviour -------------------------------------------------------------------


def test_user_agent_is_always_sent():
    """Cloudflare 403s requests with a default or absent User-Agent."""
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(request.headers)
        return httpx.Response(200, json=[])

    asyncio.run(_poly(handler).list_markets())
    assert seen["user-agent"] == USER_AGENT


def test_book_goes_to_clob_host_not_gamma():
    """Depth lives on the CLOB host; hitting gamma for it would 404."""
    urls = []

    def handler(request: httpx.Request) -> httpx.Response:
        urls.append(str(request.url))
        return httpx.Response(200, json={"bids": [], "asks": [], "timestamp": "1785672011"})

    asyncio.run(_poly(handler).get_book("tok-1"))

    assert urls[0].startswith("https://clob.polymarket.com/book")
    assert "token_id=tok-1" in urls[0]


def test_book_venue_timestamp_stays_in_payload():
    """The venue's own timestamp is never reconciled with our capture stamp (invariant 8)."""
    venue_ts = "1785672011"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"bids": [], "asks": [], "timestamp": venue_ts})

    result = asyncio.run(_poly(handler).get_book("tok-1"))

    assert result.payload["timestamp"] == venue_ts
    assert result.capture_ts_utc.tzinfo is not None


def test_trades_go_to_data_host():
    urls = []

    def handler(request: httpx.Request) -> httpx.Response:
        urls.append(str(request.url))
        return httpx.Response(200, json=[])

    asyncio.run(_poly(handler).list_trades(condition_id="0xabc"))

    assert urls[0].startswith("https://data-api.polymarket.com/trades")
    assert "market=0xabc" in urls[0]


def test_iter_markets_stops_on_short_page():
    """Gamma has no cursor — a page shorter than the limit is the last one."""
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(int(request.url.params["offset"]))
        # limit=2: two full pages, then a short one.
        rows = [{"conditionId": f"0x{len(calls)}-{i}"} for i in range(2 if len(calls) < 3 else 1)]
        return httpx.Response(200, json=rows)

    async def main():
        return [p async for p in _poly(handler).iter_markets(limit=2)]

    pages = asyncio.run(main())

    assert len(pages) == 3
    assert calls == [0, 2, 4]


def test_each_market_page_keeps_its_own_capture_stamp():
    calls = []

    async def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        await asyncio.sleep(0.05)
        rows = [{"conditionId": "0x1"}] * (2 if len(calls) < 2 else 1)
        return httpx.Response(200, json=rows)

    async def main():
        return [p async for p in _poly(handler).iter_markets(limit=2)]

    pages = asyncio.run(main())
    assert pages[0].capture_ts_utc < pages[1].capture_ts_utc


def test_clob_and_gamma_use_separate_rate_limiters():
    """Sharing one bucket would throttle the wrong host — their limits differ."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={} if "book" in str(request.url) else [])

    async def main():
        c = _poly(handler)
        assert c._limiter is not c._clob_limiter
        await c.get_book("tok-1")
        # The gamma limiter must be restored after a CLOB call.
        return c._limiter

    gamma_limiter = asyncio.run(main())
    assert gamma_limiter is not None


def test_json_decode_failure_falls_back_to_raw_string():
    """A malformed field must not crash ingestion — bronze stores raw regardless."""
    parsed = parse_gamma_market({"outcomes": "not-json{"})
    assert parsed["outcomes"] == "not-json{"
