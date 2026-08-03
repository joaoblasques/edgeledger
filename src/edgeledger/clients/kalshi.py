"""Kalshi API client. STUB — due week 1.

Endpoints to wrap (see 05-Venues/Kalshi.md for the full reference):
  GET /markets                       no auth
  GET /markets/{ticker}               no auth
  GET /markets/trades                 no auth, paginated via cursor
  GET /markets/{ticker}/orderbook     AUTH REQUIRED — KALSHI-ACCESS-KEY/-SIGNATURE/-TIMESTAMP,
                                       RSA-PSS per-request signing
  GET /events/{event_ticker}          no auth
  GET /series/{series_ticker}         no auth
  GET /historical/markets             no auth — settled markets move here; poll both.

Intended shape:

    class KalshiClient(VenueClient):
        def sign_request(self, method: str, path: str, timestamp_ms: int) -> str: ...
        async def list_markets(self, status: str = "open") -> list[dict]: ...
        async def get_orderbook(self, ticker: str) -> dict: ...
        async def list_trades(self, cursor: str | None = None) -> tuple[list[dict], str | None]: ...
        async def list_historical_markets(self, **filters) -> list[dict]: ...

Gotcha to encode in tests once implemented: settled markets vanish from /markets and
must be looked up in /historical/markets, or resolutions silently disappear.
"""
