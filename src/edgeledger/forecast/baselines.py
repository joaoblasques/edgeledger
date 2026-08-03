"""Naive baseline models. STUB — due week 3 (month-01 spec §6).

Two models, deliberately trivial — the control that validates the pipeline end to
end, and the floor every later model must beat:

    def market_mirror(market_snapshot: dict, t_minus_24h_price: Decimal) -> Decimal:
        '''p_hat = mkt_yes_mid at T-24h before close. Zero edge by construction.
        model_name="market_mirror", model_version="1.0.0".'''

    def base_rate(outcome_class: str, historical_frequencies: dict[str, Decimal]) -> Decimal:
        '''p_hat = historical frequency of the outcome class (e.g. home-team win rate).
        Genuinely naive — expected to lose to the market.
        model_name="base_rate", model_version="1.0.0".'''

Both feed `forecast/log.py::append_forecast` via DAG 4 (`forecast_baseline`, every 6h).
"""
