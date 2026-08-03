"""Airflow DAG: ingest_polymarket. STUB with task graph, no logic — due week 2.

Schedule: */15 * * * * (every 15 min)

Task graph:
    discover_markets_gamma    # GET /markets?active=true, paginate
      -> extract_token_ids     # conditionId + clobTokenIds -> dim table
      -> fetch_books_clob      # GET /book?token_id=... for tracked tokens
      -> fetch_trades_data_api

Gotcha: Gamma's 60 req/min limit will bite immediately. Batch discovery, cache
conditionId -> tokenIds mapping, and only re-fetch metadata daily (not every run).
"""

# from airflow.decorators import dag, task
#
# @dag(schedule="*/15 * * * *", catchup=False)
# def ingest_polymarket():
#     @task
#     def discover_markets_gamma(): ...
#     @task
#     def extract_token_ids(markets): ...
#     @task
#     def fetch_books_clob(token_ids): ...
#     @task
#     def fetch_trades_data_api(): ...
#
#     markets = discover_markets_gamma()
#     token_ids = extract_token_ids(markets)
#     fetch_books_clob(token_ids)
#     fetch_trades_data_api()
#
# ingest_polymarket()
