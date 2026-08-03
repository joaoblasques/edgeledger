"""Tests for the venue client base: rate limiting, retry/backoff, capture stamping.

The capture-stamp tests are the ones that matter for the invariants — a client that
stamps from a venue timestamp, or stamps late, silently corrupts every point-in-time
guarantee downstream (CLAUDE.md invariants 3, 7, 8).
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import httpx
import pytest

from edgeledger.clients.base import Captured, TokenBucket, VenueClient


def _client(handler, **kwargs) -> VenueClient:
    """VenueClient wired to a mock transport, with rate limiting effectively disabled."""
    transport = httpx.MockTransport(handler)
    http = httpx.AsyncClient(transport=transport, base_url="https://venue.test")
    return VenueClient("https://venue.test", TokenBucket(rate_per_min=600_000), client=http, **kwargs)


# --- capture stamping ----------------------------------------------------------------


def test_capture_ts_is_utc_and_ours_not_the_venues():
    """capture_ts_utc comes from our clock at receipt — never from the venue's payload."""
    venue_ts = "2020-01-01T00:00:00Z"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"timestamp": venue_ts, "value": 1})

    before = datetime.now(UTC)
    result = asyncio.run(_client(handler).get("/markets"))
    after = datetime.now(UTC)

    assert isinstance(result, Captured)
    assert result.capture_ts_utc.tzinfo is not None
    assert result.capture_ts_utc.utcoffset() == UTC.utcoffset(None), "invariant 7: UTC only"
    assert before <= result.capture_ts_utc <= after
    # The venue's own timestamp survives untouched inside the payload, unreconciled.
    assert result.payload["timestamp"] == venue_ts


# --- retry / backoff -----------------------------------------------------------------


def test_retries_on_429_then_succeeds():
    attempts = []

    def handler(request: httpx.Request) -> httpx.Response:
        attempts.append(1)
        if len(attempts) < 3:
            return httpx.Response(429, headers={"Retry-After": "0"}, json={})
        return httpx.Response(200, json={"ok": True})

    result = asyncio.run(_client(handler).get("/markets"))

    assert len(attempts) == 3
    assert result.payload == {"ok": True}


def test_does_not_retry_on_400():
    """A 4xx that isn't 429 is our bug — retrying it just burns rate-limit quota."""
    attempts = []

    def handler(request: httpx.Request) -> httpx.Response:
        attempts.append(1)
        return httpx.Response(400, json={"error": "bad param"})

    with pytest.raises(httpx.HTTPStatusError):
        asyncio.run(_client(handler).get("/markets"))

    assert len(attempts) == 1, "400 must fail immediately, not retry"


def test_gives_up_after_max_attempts():
    attempts = []

    def handler(request: httpx.Request) -> httpx.Response:
        attempts.append(1)
        return httpx.Response(503, headers={"Retry-After": "0"}, json={})

    with pytest.raises(httpx.HTTPStatusError):
        asyncio.run(_client(handler, max_attempts=3).get("/markets"))

    assert len(attempts) == 3


def test_retry_after_header_is_honoured():
    client = _client(lambda r: httpx.Response(200, json={}))
    exc = httpx.HTTPStatusError(
        "429",
        request=httpx.Request("GET", "https://venue.test/x"),
        response=httpx.Response(429, headers={"Retry-After": "7"}),
    )
    assert client._backoff_delay(1, exc) == 7.0


def test_backoff_is_exponential_without_retry_after():
    client = _client(lambda r: httpx.Response(200, json={}))
    exc = httpx.RequestError("boom", request=httpx.Request("GET", "https://venue.test/x"))
    delays = [client._backoff_delay(n, exc) for n in (1, 2, 3, 4)]
    assert delays == [1.0, 2.0, 4.0, 8.0]


# --- token bucket --------------------------------------------------------------------


def test_token_bucket_limits_rate():
    """A bucket with no burst headroom must pace acquisitions, not release them at once."""

    async def drain() -> float:
        # 60/min = 1/sec, burst of 1: the 3rd acquire needs ~2s of refill.
        bucket = TokenBucket(rate_per_min=60, burst=1)
        loop = asyncio.get_event_loop()
        start = loop.time()
        for _ in range(3):
            await bucket.acquire()
        return loop.time() - start

    assert asyncio.run(drain()) >= 1.5


def test_token_bucket_allows_burst_up_to_capacity():
    async def drain() -> float:
        bucket = TokenBucket(rate_per_min=60, burst=5)
        loop = asyncio.get_event_loop()
        start = loop.time()
        for _ in range(5):
            await bucket.acquire()
        return loop.time() - start

    assert asyncio.run(drain()) < 0.5, "a full bucket should not throttle"


def test_token_bucket_rejects_nonsense_rate():
    with pytest.raises(ValueError):
        TokenBucket(rate_per_min=0)
