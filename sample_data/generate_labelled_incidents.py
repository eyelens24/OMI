"""Generate a labelled synthetic dataset for exercising the ML pipeline only."""
import csv
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path


OUTPUT = Path(__file__).parent / "labelled_incidents.synthetic.csv"
FIELDS = [
    "timestamp", "strategy_id", "symbol", "label", "review_status", "earnings_revision_pct", "revenue_growth_yoy",
    "eps_growth_yoy", "earnings_surprise_pct", "free_cash_flow_yield", "debt_to_ebitda", "interest_coverage",
    "alpha_score", "information_coefficient", "rank_ic", "weight_error_bps", "target_actual_weight_gap_bps",
    "fundamental_age_days", "as_of_lag_days", "revision_lag_days", "slippage_bps", "fill_rate", "latency_ms",
]
LABELS = ("earnings_estimate_cut", "alpha_score_decay", "target_actual_weight_gap", "fundamental_data_stale", "debt_leverage_increase")
SYMBOLS = ("AAPL", "MSFT", "NVDA", "JPM", "XOM")


def incident(label, index):
    wobble = math.sin(index * 1.7) * .12
    row = {
        "timestamp": (datetime(2022, 1, 3, tzinfo=timezone.utc) + timedelta(days=index)).isoformat(),
        "strategy_id": f"synthetic_strategy_{index % 4}", "symbol": SYMBOLS[index % len(SYMBOLS)],
        "label": label, "review_status": "accepted", "earnings_revision_pct": .5 + wobble,
        "revenue_growth_yoy": 11 + wobble, "eps_growth_yoy": 13 + wobble, "earnings_surprise_pct": 2 + wobble,
        "free_cash_flow_yield": 4.5 + wobble, "debt_to_ebitda": 1.5 + wobble / 4, "interest_coverage": 9 + wobble,
        "alpha_score": .75 + wobble / 10, "information_coefficient": .08 + wobble / 100,
        "rank_ic": .09 + wobble / 100, "weight_error_bps": 8 + abs(wobble) * 3,
        "target_actual_weight_gap_bps": 11 + abs(wobble) * 4, "fundamental_age_days": 1 + abs(wobble),
        "as_of_lag_days": .5 + abs(wobble), "revision_lag_days": .3 + abs(wobble),
        "slippage_bps": 3 + abs(wobble), "fill_rate": .995 - abs(wobble) / 100, "latency_ms": 10 + abs(wobble) * 5,
    }
    if label == "earnings_estimate_cut":
        row.update(earnings_revision_pct=-8 + wobble, revenue_growth_yoy=2 + wobble, eps_growth_yoy=-4 + wobble, earnings_surprise_pct=-7 + wobble)
    elif label == "alpha_score_decay":
        row.update(alpha_score=-.18 + wobble / 10, information_coefficient=-.05 + wobble / 100, rank_ic=-.06 + wobble / 100)
    elif label == "target_actual_weight_gap":
        row.update(weight_error_bps=96 + abs(wobble) * 3, target_actual_weight_gap_bps=118 + abs(wobble) * 4, slippage_bps=11 + abs(wobble))
    elif label == "fundamental_data_stale":
        row.update(fundamental_age_days=12 + abs(wobble), as_of_lag_days=6 + abs(wobble), revision_lag_days=4 + abs(wobble))
    elif label == "debt_leverage_increase":
        row.update(debt_to_ebitda=4.8 + wobble / 4, interest_coverage=1.7 + wobble, free_cash_flow_yield=1.2 + wobble)
    return row


def main():
    rows = [incident(LABELS[index % len(LABELS)], index) for index in range(500)]
    with OUTPUT.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows)} synthetic labelled incidents to {OUTPUT}")


if __name__ == "__main__":
    main()
