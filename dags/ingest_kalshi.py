"""Airflow DAG: ingest_kalshi. STUB with task graph, no logic — due week 2.

Schedule: */15 * * * * (every 15 min)

Task graph:
    discover_markets          # GET /markets?status=open, paginate
      -> snapshot_market_state  # extract prices/volume per market
      -> fetch_orderbooks       # top-N liquid markets only (auth'd, rate-limited)
      -> fetch_trades           # GET /markets/trades, cursor from ingest_state watermark

Watermark for trades stored in a small `ingest_state` Delta table keyed by
(venue, stream) — read at task start, written at task end, so a restart resumes
from the last successful cursor rather than the beginning.
"""

# from airflow.decorators import dag, task
#
# @dag(schedule="*/15 * * * *", catchup=False)
# def ingest_kalshi():
#     @task
#     def discover_markets(): ...
#     @task
#     def snapshot_market_state(markets): ...
#     @task
#     def fetch_orderbooks(markets): ...
#     @task
#     def fetch_trades(): ...
#
#     markets = discover_markets()
#     snapshot_market_state(markets)
#     fetch_orderbooks(markets)
#     fetch_trades()
#
# ingest_kalshi()
