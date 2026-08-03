"""Polymarket API client (Gamma + CLOB + Data services). STUB — due week 1.

Three base URLs, three purposes (see 05-Venues/Polymarket.md):
  Gamma  https://gamma-api.polymarket.com    discover events/markets, metadata (~60 req/min)
  CLOB   https://clob.polymarket.com         live market state, depth (~100 req/min read)
  Data   https://data-api.polymarket.com     /trades, account+market activity

All read APIs are unauthenticated.

Intended shape:

    class PolymarketClient(VenueClient):
        async def list_markets_gamma(self, active: bool = True) -> list[dict]: ...
        async def get_book_clob(self, token_id: str) -> dict: ...
        async def list_trades_data_api(self, market: str) -> list[dict]: ...

Gotchas to encode once implemented:
  - Multi-outcome markets are bundles of linked binaries (each with its own conditionId
    + token pair) — never model as a single row, or probabilities won't sum to 1.
  - Cache conditionId -> clobTokenIds; re-fetch Gamma metadata daily only, to stay under
    the 60 req/min limit.
"""
