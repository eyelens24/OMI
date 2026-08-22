"""Regenerate the ready-to-upload Quant Doctor sample CSV files."""
import csv
import math
import sys
from pathlib import Path

OUTPUT = Path(__file__).parent
sys.path.insert(0, str(OUTPUT.parent))
from server import synthetic_dataset
COMBINED_FIELDS = ["timestamp", "pnl", "volatility", "volume_ratio", "spread_bps", "slippage_bps", "signal_strength", "news_risk"]
MARKET_FIELDS = ["timestamp", "price", "return", "volatility", "volume_ratio", "spread_bps", "slippage_bps", "signal_strength", "news_risk"]
STRATEGY_FIELDS = ["timestamp", "pnl", "equity", "expected_pnl", "implementation_shortfall"]
FAULT_MARKET_FIELDS = MARKET_FIELDS + ["symbol", "data_age_ms", "missing_rate", "stale_ticks", "vendor_diff_bps", "clock_skew_ms"]
FAULT_STRATEGY_FIELDS = STRATEGY_FIELDS + ["symbol", "side", "quantity", "notional", "hit_rate", "feature_drift_score", "gross_exposure", "net_exposure", "leverage", "concentration", "position_size", "fill_rate", "reject_rate", "latency_ms", "fees", "broker_position_mismatch", "api_error_rate", "api_disconnects", "restart_count", "strategy_version", "parameter_hash"]
FUNDAMENTAL_FIELDS = ["timestamp", "symbol", "price", "return", "pnl", "equity", "earnings_revision_pct", "earnings_surprise_pct", "revenue_growth_yoy", "eps_growth_yoy", "free_cash_flow_yield", "valuation_percentile", "debt_to_ebitda", "interest_coverage", "alpha_score", "expected_return", "information_coefficient", "rank_ic", "weight_error_bps", "target_actual_weight_gap_bps", "fundamental_age_days", "as_of_lag_days", "revision_lag_days"]
MIXED_INCIDENT_FIELDS = FUNDAMENTAL_FIELDS + ["action", "target_position", "target_weight", "decision_reason"]
FUNDAMENTAL_MARKET_FIELDS = [field for field in FUNDAMENTAL_FIELDS if field not in {"pnl", "equity"}]
FUNDAMENTAL_STRATEGY_FIELDS = ["timestamp", "symbol", "pnl", "equity"]


def write_sample(name, rows, fields):
    with (OUTPUT / name).open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows({field: row[field] for field in fields} for row in rows)


def inject_non_fundamental_faults(rows):
    """Add deterministic, labelled operational faults after the regime break."""
    enriched = []
    symbols = ("AAPL", "MSFT", "NVDA", "JPM", "XOM")
    quantities = (500, 280, 190, 340, 160)
    for index, original in enumerate(rows):
        row = dict(original)
        # The market regime break begins earlier; operational faults begin later
        # so the initial quarter remains a clean baseline for detector tests.
        fault = index >= 100
        wobble = (index % 7) / 100
        row.update({
            "symbol": symbols[index % len(symbols)],
            "side": "buy" if index % 3 else "sell",
            "quantity": quantities[index % len(quantities)],
            "notional": round(quantities[index % len(quantities)] * row["price"], 2),
            "data_age_ms": round(45 + wobble * 20 + (1450 if fault else 0), 2),
            "missing_rate": round(.002 + (.085 if fault else 0), 4),
            "stale_ticks": 0 if not fault else 4 + index % 3,
            "vendor_diff_bps": round(.08 + (.92 if fault else 0) + wobble, 3),
            "clock_skew_ms": round(2 + (68 if fault else 0), 2),
            "hit_rate": round(.58 - (.23 if fault else 0) - wobble / 4, 3),
            "feature_drift_score": round(.04 + (.61 if fault else 0) + wobble, 3),
            "gross_exposure": 820000 + (1650000 if fault else 0) + index * 600,
            "net_exposure": 190000 + (520000 if fault else 0),
            "leverage": round(1.15 + (2.05 if fault else 0), 2),
            "concentration": round(.17 + (.42 if fault else 0), 3),
            "position_size": 100000 + (360000 if fault else 0),
            "fill_rate": round(.992 - (.135 if fault else 0) - wobble / 10, 3),
            "reject_rate": round(.003 + (.064 if fault else 0), 3),
            "latency_ms": 13 + (280 if fault else 0) + index % 5,
            "fees": round(86 + (214 if fault else 0) + index % 8, 2),
            "broker_position_mismatch": 0 if not fault else 1,
            "api_error_rate": round(.001 + (.071 if fault else 0), 3),
            "api_disconnects": 0 if not fault else 2 + index % 2,
            "restart_count": 0 if not fault else 1,
            "strategy_version": "v1.4.0" if not fault else "v1.5.0",
            "parameter_hash": "c8a1" if not fault else "f29d",
        })
        enriched.append(row)
    return enriched


def fundamental_thesis_failure(rows):
    """A labelled, deterministic example of a deteriorating long-equity thesis.

    It is deliberately synthetic: the fields are not live company fundamentals.
    The deterioration begins after the first quarter so the app has a clean
    baseline and a later incident to compare against.
    """
    enriched = []
    symbols = ("AAPL", "MSFT", "NVDA", "JPM", "XOM")
    for index, original in enumerate(rows):
        row = dict(original)
        failure = index >= 110
        wobble = math.sin(index / 9) * .22
        return_drag = -.0048 if failure else 0
        stock_return = float(row["return"]) + return_drag + wobble / 10000
        row.update({
            "symbol": symbols[index % len(symbols)],
            "return": round(stock_return, 6),
            "earnings_revision_pct": round(.65 + wobble - (8.3 if failure else 0), 3),
            "earnings_surprise_pct": round(2.1 + wobble - (10.7 if failure else 0), 3),
            "revenue_growth_yoy": round(11.4 + wobble - (9.2 if failure else 0), 3),
            "eps_growth_yoy": round(13.7 + wobble - (17.4 if failure else 0), 3),
            "free_cash_flow_yield": round(4.6 + wobble / 3 - (2.05 if failure else 0), 3),
            "valuation_percentile": round(.52 + wobble / 20 + (.34 if failure else 0), 3),
            "debt_to_ebitda": round(1.35 + wobble / 4 + (2.05 if failure else 0), 3),
            "interest_coverage": round(9.1 + wobble - (6.4 if failure else 0), 3),
            # Internal research and portfolio-decision artefacts. These make
            # the sample a fundamental-alpha debugging case, not a generic
            # fundamental screen.
            "alpha_score": round(.72 + wobble / 10 - (.61 if failure else 0), 3),
            "expected_return": round(1.45 + wobble / 3 - (2.2 if failure else 0), 3),
            "information_coefficient": round(.075 + wobble / 100 - (.108 if failure else 0), 3),
            "rank_ic": round(.092 + wobble / 100 - (.125 if failure else 0), 3),
            "weight_error_bps": round(8 + abs(wobble) * 4 + (67 if failure else 0), 2),
            "target_actual_weight_gap_bps": round(11 + abs(wobble) * 5 + (79 if failure else 0), 2),
            "fundamental_age_days": round(1.1 + abs(wobble) + (5.8 if failure else 0), 2),
            "as_of_lag_days": round(.45 + abs(wobble) / 2 + (2.6 if failure else 0), 2),
            "revision_lag_days": round(.3 + abs(wobble) / 3 + (3.7 if failure else 0), 2),
        })
        # A long-biased strategy: the controlled stock decline is intentionally
        # carried into realised P&L, making the example's expected mechanism
        # inspectable from fundamentals through to the strategy outcome.
        row["pnl"] = round(float(row["pnl"]) + stock_return * 620000, 2)
        enriched.append(row)
    equity = 0.0
    for row in enriched:
        equity += row["pnl"]
        row["equity"] = round(equity, 2)
    return enriched


def mixed_incident(rows):
    """A multi-cause incident for testing per-loss diagnoses.

    Each ticker has its own deliberately different failure after the shared
    baseline: AAPL growth/EPS, MSFT alpha ranking, NVDA portfolio translation,
    JPM stale point-in-time data, and XOM balance-sheet leverage. It is
    synthetic and labelled for testing the app, not a model of real names.
    """
    enriched = []
    symbols = ("AAPL", "MSFT", "NVDA", "JPM", "XOM")
    for index, original in enumerate(rows):
        row = dict(original)
        wobble = math.sin(index / 7) * .18
        symbol = symbols[index % len(symbols)]
        if index < 90:
            phase, return_drag, pnl_drag = "baseline", -.0002, 0
        else:
            phase, return_drag, pnl_drag = {
                "AAPL": ("growth", -.011, -2200),
                "MSFT": ("alpha", -.015, -1700),
                "NVDA": ("translation", -.001, -11200),
                "JPM": ("stale_data", -.003, -6800),
                "XOM": ("balance_sheet", -.010, -2400),
            }[symbol]

        eps_growth = 13.2 + wobble - (18.5 if phase == "growth" else 0)
        revenue_growth = 10.8 + wobble - (8.8 if phase == "growth" else 0)
        rank_ic = .094 + wobble / 100 - (.15 if phase == "alpha" else 0)
        information_coefficient = .078 + wobble / 100 - (.11 if phase == "alpha" else 0)
        alpha_score = .73 + wobble / 10 - (.62 if phase == "alpha" else 0)
        target_gap = 10 + abs(wobble) * 4 + (108 if phase == "translation" else 0)
        weight_error = 7 + abs(wobble) * 4 + (94 if phase == "translation" else 0)
        fundamental_age = 1.0 + abs(wobble) + (9.5 if phase == "stale_data" else 0)
        as_of_lag = .4 + abs(wobble) / 2 + (4.7 if phase == "stale_data" else 0)
        stock_return = return_drag + wobble / 10000
        rationale = {
            "baseline": "Fundamental alpha score supported the long target.",
            "growth": "Existing long target remained in place while the growth evidence deteriorated.",
            "alpha": "The model still held the name although the alpha ranking was decaying.",
            "translation": "Target remained positive; realised weight diverged from the recorded target.",
            "stale_data": "The decision used an older recorded fundamental snapshot.",
            "balance_sheet": "The existing long target remained despite worsening debt-service risk.",
        }[phase]
        row.update({
            "symbol": symbol, "return": round(stock_return, 6),
            "earnings_revision_pct": round(.7 + wobble - (7.5 if phase == "growth" else 0), 3),
            "earnings_surprise_pct": round(2.3 + wobble - (9.0 if phase == "growth" else 0), 3),
            "revenue_growth_yoy": round(revenue_growth, 3), "eps_growth_yoy": round(eps_growth, 3),
            "free_cash_flow_yield": round(4.7 + wobble / 3, 3), "valuation_percentile": round(.54 + wobble / 20, 3),
            "debt_to_ebitda": round(1.4 + wobble / 4 + (3.1 if phase == "balance_sheet" else 0), 3), "interest_coverage": round(9.4 + wobble - (6.8 if phase == "balance_sheet" else 0), 3),
            "alpha_score": round(alpha_score, 3), "expected_return": round(1.5 - (1.1 if phase == "alpha" else 0) + wobble / 3, 3),
            "information_coefficient": round(information_coefficient, 3), "rank_ic": round(rank_ic, 3),
            "weight_error_bps": round(weight_error, 2), "target_actual_weight_gap_bps": round(target_gap, 2),
            "fundamental_age_days": round(fundamental_age, 2), "as_of_lag_days": round(as_of_lag, 2),
            "revision_lag_days": round(.3 + abs(wobble) / 3 + (2.1 if phase == "stale_data" else 0), 2),
            "action": "buy", "target_position": 1.0, "target_weight": round(.035 + (0.006 if phase != "alpha" else -.012), 3),
            "decision_reason": rationale,
        })
        row["pnl"] = round(850 + math.sin(index / 4) * 280 + stock_return * 520000 + pnl_drag, 2)
        enriched.append(row)
    equity = 0.0
    for row in enriched:
        equity += row["pnl"]
        row["equity"] = round(equity, 2)
    return enriched


if __name__ == "__main__":
    all_rows = synthetic_dataset()
    normal, failure = all_rows[:180], all_rows[360:]
    write_sample("market_normal.csv", normal, COMBINED_FIELDS)
    write_sample("market_failure.csv", failure, COMBINED_FIELDS)
    write_sample("market_failure_market.csv", failure, MARKET_FIELDS)
    write_sample("market_failure_strategy.csv", failure, STRATEGY_FIELDS)
    fault_rows = inject_non_fundamental_faults(failure)
    write_sample("non_fundamental_failure_market.csv", fault_rows, FAULT_MARKET_FIELDS)
    write_sample("non_fundamental_failure_strategy.csv", fault_rows, FAULT_STRATEGY_FIELDS)
    fundamental_rows = fundamental_thesis_failure(failure)
    write_sample("fundamental_failure.csv", fundamental_rows, FUNDAMENTAL_FIELDS)
    write_sample("fundamental_failure_market.csv", fundamental_rows, FUNDAMENTAL_MARKET_FIELDS)
    write_sample("fundamental_failure_strategy.csv", fundamental_rows, FUNDAMENTAL_STRATEGY_FIELDS)
    write_sample("mixed_incident.csv", mixed_incident(failure), MIXED_INCIDENT_FIELDS)
    print("Wrote combined samples, split samples, non-fundamental samples, the fundamental-thesis sample, and the mixed incident sample")
