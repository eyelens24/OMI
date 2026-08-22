"""Known-truth local scenarios for OMI demo and regression testing."""

def scenario_catalog():
    common = {"decision": {"strategy_version": "demo-v1", "parameter_hash": "demo"}, "target": {"weight": .05}, "fill": {"quantity": 50, "price": 100}, "position": {"quantity": 50}, "pnl": {"realised_pnl": -500}}
    return [
        {"id": "stale-input", "title": "Stale fundamental snapshot", "ground_truth": "fundamental_data_staleness", "evidence": {**common, "fundamental_snapshot": {"available_at": "before-decision", "age_days": 3}}},
        {"id": "execution-gap", "title": "Target-to-fill translation gap", "ground_truth": "portfolio_translation_gap", "evidence": {**common, "fill": {"quantity": 38, "price": 101, "slippage_bps": 100}}},
        {"id": "market-shock", "title": "Market move without data fault", "ground_truth": "market_regime_move", "evidence": {**common, "market": {"return": -.08, "available_at": "decision-time"}}},
    ]
