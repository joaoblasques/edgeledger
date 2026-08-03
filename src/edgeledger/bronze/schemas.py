"""Pydantic models for bronze tables. STUB — due week 1-2.

Mirrors month-01 spec §4 verbatim. Bronze is raw: full JSON payload verbatim in
`payload`, plus a few extracted keys for partitioning. Never transform on write —
schema drift is a silver-layer problem, not an ingestion failure.

Intended models (one per table):

    class VenueMarketSnapshot(BaseModel):
        capture_ts_utc: datetime      # when WE fetched — never venue-derived
        run_id: str
        venue: Literal["kalshi", "polymarket"]
        venue_market_id: str          # ticker | conditionId
        payload: str                  # full JSON, verbatim
        ingest_date: date             # partition key

    class VenueOrderbookSnapshot(BaseModel):
        capture_ts_utc: datetime
        venue: Literal["kalshi", "polymarket"]
        venue_market_id: str
        outcome_side: Literal["yes", "no"]
        bids: str                     # JSON [[price, size], ...]
        asks: str
        payload: str
        ingest_date: date

    class VenueTrade(BaseModel):
        capture_ts_utc: datetime
        venue: Literal["kalshi", "polymarket"]
        venue_market_id: str
        venue_trade_id: str            # dedupe key
        trade_ts_utc: datetime         # venue's own timestamp — stored separately,
                                        # never reconciled with capture_ts_utc (invariant 8)
        price: Decimal
        size: Decimal
        payload: str
        ingest_date: date

    class Resolution(BaseModel):
        capture_ts_utc: datetime
        venue: Literal["kalshi", "polymarket"]
        venue_market_id: str
        resolved_outcome: Literal["yes", "no", "invalid"]
        resolution_ts_utc: datetime
        payload: str
"""
