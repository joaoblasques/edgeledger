"""Shared HTTP client base: retry, backoff, token-bucket rate limiting, capture_ts stamping.

Venue-agnostic. Signing (Kalshi's RSA-PSS headers) belongs in `kalshi.py` — this module
never learns what a venue's auth looks like.

The one thing here that is a correctness contract rather than plumbing: `capture_ts_utc`
is stamped from OUR clock at the moment the response body is received, and is never
derived from a venue timestamp (CLAUDE.md invariants 3, 7, 8). Everything downstream that
respects the point-in-time cutoff depends on that stamp being honest.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Self

import httpx

logger = logging.getLogger(__name__)

# Retried on: the venue is rate-limiting us, or is briefly unavailable. A 4xx that isn't
# 429 is our bug (bad params, bad signature) and retrying it just burns quota.
RETRY_STATUS = frozenset({429, 500, 502, 503, 504})


class TokenBucket:
    """Async token bucket. Refills continuously at `rate_per_min`, capped at `burst`.

    Continuous refill rather than a fixed window: a window lets the full quota be spent in
    its first instant, which is exactly the burst that trips a venue's limiter.
    """

    def __init__(self, rate_per_min: int, burst: int | None = None) -> None:
        if rate_per_min <= 0:
            raise ValueError("rate_per_min must be positive")
        self._rate_per_sec = rate_per_min / 60.0
        self._capacity = float(burst if burst is not None else rate_per_min)
        self._tokens = self._capacity
        self._last: float | None = None
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        """Block until a token is available, then consume it."""
        # Monotonic loop clock, read here rather than at construction: there is no running
        # loop in __init__, and wall-clock jumps (NTP, DST) must not hand out free tokens.
        clock = asyncio.get_running_loop().time
        # ponytail: one lock over the whole bucket. Fine at these rates; if a venue ever
        # needs thousands of req/min, shard the bucket per-host.
        async with self._lock:
            while True:
                now = clock()
                if self._last is None:
                    self._last = now
                self._tokens = min(
                    self._capacity, self._tokens + (now - self._last) * self._rate_per_sec
                )
                self._last = now
                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    return
                await asyncio.sleep((1.0 - self._tokens) / self._rate_per_sec)


@dataclass(frozen=True, slots=True)
class Captured:
    """A venue payload plus the instant WE received it.

    `capture_ts_utc` is our clock, never the venue's. Venue-supplied timestamps stay inside
    `payload` and are extracted separately downstream — the two are never reconciled into
    one field (invariant 8).
    """

    capture_ts_utc: datetime
    payload: Any


class VenueClient:
    """Base class for the per-venue clients. Async context manager.

    Subclasses override `_auth_headers` to sign a request; everything else — retry,
    backoff, rate limiting, capture stamping — is inherited unchanged.
    """

    def __init__(
        self,
        base_url: str,
        rate_limiter: TokenBucket,
        *,
        max_attempts: int = 5,
        timeout: float = 20.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        self._base_url = base_url.rstrip("/")
        self._limiter = rate_limiter
        self._max_attempts = max_attempts
        self._client = client or httpx.AsyncClient(base_url=self._base_url, timeout=timeout)

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    def _auth_headers(self, method: str, path: str) -> dict[str, str]:
        """Per-request auth headers. Unauthenticated by default; venues override."""
        return {}

    async def get(self, path: str, **kwargs: Any) -> Captured:
        """GET `path`, rate-limited and retried, returning the payload with our capture stamp.

        Raises the final `httpx.HTTPStatusError` / `httpx.RequestError` if every attempt fails.
        """
        last_exc: Exception | None = None

        for attempt in range(1, self._max_attempts + 1):
            await self._limiter.acquire()
            try:
                response = await self._client.get(
                    path, headers=self._auth_headers("GET", path), **kwargs
                )
                # Stamp at receipt, before any parsing — parse cost must not inflate the
                # gap between "what the venue showed us" and the time we claim we saw it.
                captured_at = datetime.now(UTC)

                if response.status_code in RETRY_STATUS:
                    response.raise_for_status()

                response.raise_for_status()
                return Captured(capture_ts_utc=captured_at, payload=response.json())

            except (httpx.HTTPStatusError, httpx.RequestError) as exc:
                status = getattr(getattr(exc, "response", None), "status_code", None)
                # A non-retryable 4xx (bad params, bad signature) will never succeed on
                # a retry — fail now rather than burning the rate-limit quota.
                if status is not None and status not in RETRY_STATUS:
                    raise
                last_exc = exc
                if attempt == self._max_attempts:
                    break
                delay = self._backoff_delay(attempt, exc)
                logger.warning(
                    "venue request failed, retrying",
                    extra={
                        "path": path,
                        "attempt": attempt,
                        "max_attempts": self._max_attempts,
                        "status": status,
                        "retry_in_s": round(delay, 2),
                    },
                )
                await asyncio.sleep(delay)

        assert last_exc is not None  # only reachable after a failed attempt
        raise last_exc

    def _backoff_delay(self, attempt: int, exc: Exception) -> float:
        """Exponential backoff, but honour a venue's Retry-After when it sends one."""
        response = getattr(exc, "response", None)
        if response is not None:
            retry_after = response.headers.get("Retry-After")
            if retry_after:
                try:
                    return max(0.0, float(retry_after))
                except ValueError:
                    # Retry-After may be an HTTP-date; fall through to exponential.
                    pass
        # ponytail: deterministic backoff, no jitter — this is a single-writer poller, not
        # a fleet, so there is no thundering herd to spread out. Add jitter if that changes.
        return float(2 ** (attempt - 1))
