"""Train and time-evaluate a conservative incident-label baseline.

The model is a standardised nearest-centroid classifier. It is intentionally
simple and inspectable: it can be replaced later, but it establishes the right
time-safe data split, label contract, confidence threshold, and abstention
behaviour without requiring a third-party ML dependency.
"""
import argparse
import csv
import json
import math
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from statistics import mean, pstdev


REQUIRED = {"timestamp", "strategy_id", "symbol", "label", "review_status"}
DEFAULT_FEATURES = (
    "earnings_revision_pct", "revenue_growth_yoy", "eps_growth_yoy", "earnings_surprise_pct",
    "free_cash_flow_yield", "debt_to_ebitda", "interest_coverage", "alpha_score", "information_coefficient",
    "rank_ic", "weight_error_bps", "target_actual_weight_gap_bps", "fundamental_age_days", "as_of_lag_days",
    "revision_lag_days", "slippage_bps", "fill_rate", "latency_ms",
)
UNKNOWN = "unknown_or_insufficient_evidence"


def number(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def read_rows(path):
    with Path(path).open(newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or not REQUIRED <= set(reader.fieldnames):
            missing = sorted(REQUIRED - set(reader.fieldnames or []))
            raise ValueError(f"Missing required training columns: {', '.join(missing)}")
        rows = [row for row in reader if row.get("review_status", "").strip().lower() == "accepted"]
    if len(rows) < 40:
        raise ValueError("At least 40 accepted reviewer-labelled incidents are required.")
    return sorted(rows, key=lambda row: row["timestamp"])


def usable_features(rows):
    return [field for field in DEFAULT_FEATURES if sum(number(row.get(field)) is not None for row in rows) >= max(20, len(rows) // 3)]


def vector(row, features, means, scales):
    return [(number(row.get(field)) if number(row.get(field)) is not None else means[field] - means[field]) / scales[field] for field in features]


def distance(left, right):
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(left, right)))


def train(rows, features):
    means = {field: mean([number(row.get(field)) for row in rows if number(row.get(field)) is not None]) for field in features}
    scales = {field: pstdev([number(row.get(field)) for row in rows if number(row.get(field)) is not None]) or 1.0 for field in features}
    grouped = defaultdict(list)
    for row in rows:
        grouped[row["label"]].append(vector(row, features, means, scales))
    centroids = {label: [mean(values[index] for values in vectors) for index in range(len(features))] for label, vectors in grouped.items()}
    # The threshold is learned from accepted examples. Values outside the 95th
    # percentile of their class distance abstain instead of being forced into a
    # familiar label.
    thresholds = {}
    for label, vectors in grouped.items():
        distances = sorted(distance(item, centroids[label]) for item in vectors)
        thresholds[label] = distances[min(len(distances) - 1, max(0, math.ceil(len(distances) * .95) - 1))] * 1.15 + .05
    return {"algorithm": "standardised_nearest_centroid_with_abstention", "features": features, "means": means, "scales": scales, "centroids": centroids, "thresholds": thresholds, "training_counts": dict(Counter(row["label"] for row in rows))}


def predict(row, model):
    values = vector(row, model["features"], model["means"], model["scales"])
    ranked = sorted((distance(values, centroid), label) for label, centroid in model["centroids"].items())
    nearest, label = ranked[0]
    if nearest > model["thresholds"][label]:
        return UNKNOWN, nearest
    return label, nearest


def evaluate(rows, model):
    correct = abstained = 0
    per_label = defaultdict(lambda: {"total": 0, "correct": 0})
    for row in rows:
        predicted, _ = predict(row, model)
        label = row["label"]
        per_label[label]["total"] += 1
        if predicted == UNKNOWN:
            abstained += 1
        if predicted == label:
            correct += 1
            per_label[label]["correct"] += 1
    total = len(rows)
    return {
        "test_incidents": total, "accuracy": round(correct / total, 4) if total else None,
        "abstention_rate": round(abstained / total, 4) if total else None,
        "per_label_recall": {label: round(values["correct"] / values["total"], 4) for label, values in per_label.items()},
    }


def main():
    parser = argparse.ArgumentParser(description="Train and time-evaluate a reviewer-labelled incident baseline.")
    parser.add_argument("--input", required=True, type=Path, help="Accepted reviewer-labelled incident CSV")
    parser.add_argument("--model", required=True, type=Path, help="JSON model output")
    parser.add_argument("--report", required=True, type=Path, help="JSON evaluation report output")
    parser.add_argument("--test-share", type=float, default=.25, help="Latest chronological share reserved for test")
    args = parser.parse_args()
    if not .1 <= args.test_share < .5:
        raise SystemExit("--test-share must be between 0.1 and 0.5")
    rows = read_rows(args.input)
    split = int(len(rows) * (1 - args.test_share))
    train_rows, test_rows = rows[:split], rows[split:]
    features = usable_features(train_rows)
    if len(features) < 2:
        raise SystemExit("At least two sufficiently populated numeric features are required.")
    model = train(train_rows, features)
    report = {
        "input": str(args.input), "split": "chronological: earlier incidents train, latest incidents test",
        "train_incidents": len(train_rows), "labels": sorted(model["centroids"]), "evaluation": evaluate(test_rows, model),
        "warning": "Metrics are valid only for the supplied labelled data. Synthetic labels do not demonstrate production accuracy.",
    }
    for path, payload in ((args.model, model), (args.report, report)):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
