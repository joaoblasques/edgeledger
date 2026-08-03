"""Shared HTTP client base: retry, backoff, token-bucket rate limiting, capture_ts stamping.

STUB — due week 1.

Intended shape:

    class TokenBucket:
        def __init__(self, rate_per_min: int): ...
        async def acquire(self) -> None: ...  # blocks until a token is available

    class VenueClient:
        '''Base class for kalshi.py / polymarket.py.'''

        def __init__(self, base_url: str, rate_limiter: TokenBucket): ...

        async def get(self, path: str, **kwargs) -> dict:
            '''GET with retry+backoff (httpx + tenacity-style), rate limited.
            Stamps capture_ts_utc = datetime.now(timezone.utc) on every returned payload
            envelope — this is the foundation of point-in-time correctness (CLAUDE.md
            invariant 3) and must never be venue-timestamp-derived.'''

Signing (Kalshi RSA-PSS headers) belongs in kalshi.py, not here — base.py stays
venue-agnostic.
"""
