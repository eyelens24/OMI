"""Generate the built-in CSV that exercises OMI's complete product workflow."""
import csv
from pathlib import Path

from generate_samples import mixed_incident
from server import synthetic_dataset


OUTPUT = Path(__file__).with_name("full_product_demo.csv")
LIFECYCLE = ("observation", "decision", "target", "fill", "position", "pnl")
EXTRA_FIELDS = (
    "kind", "event_id", "parent_id", "available_at", "decision_timestamp",
    "strategy_id", "strategy_version", "model_version", "feature_snapshot_id",
    "target_quantity", "fill_quantity", "position_quantity", "detail",
)


def build_rows():
    """Attach one complete lifecycle to each six-row slice of the incident CSV."""
    rows = []
    source_rows = mixed_incident(synthetic_dataset()[360:])
    equity = 0.0
    positions = {}
    symbol_cycles = {}
    for cycle in range(len(source_rows) // len(LIFECYCLE)):
        template = source_rows[cycle * len(LIFECYCLE)]
        symbol = template["symbol"]
        occurrence = symbol_cycles.get(symbol, 0)
        symbol_cycles[symbol] = occurrence + 1
        action = "HOLD" if occurrence >= 2 and occurrence % 5 == 3 else "SELL" if occurrence >= 2 and occurrence % 4 == 0 else "BUY"
        reason = (
            "The model sold because its alpha signal had deteriorated and the retained inputs showed rising risk."
            if action == "SELL" else template["decision_reason"]
        )
        if action == "HOLD":
            reason = "The model kept the existing position because the retained signals did not cross its buy or sell threshold."
        position_before = positions.get(symbol, 0)
        traded_quantity = 100 if action == "BUY" else -min(200, position_before) if action == "SELL" else 0
        position_after = position_before + traded_quantity
        positions[symbol] = position_after
        event_ids = {stage: f"{stage}-{cycle:03d}" for stage in LIFECYCLE}
        for offset, kind in enumerate(LIFECYCLE):
            source = dict(template)
            source["timestamp"] = source_rows[cycle * len(LIFECYCLE) + offset]["timestamp"]
            source["action"] = action if kind == "decision" else ""
            source["target_position"] = str(position_after)
            source["target_quantity"] = str(position_after) if kind == "target" else ""
            source["target_weight"] = "-0.035" if action == "SELL" else template["target_weight"]
            source["decision_reason"] = reason
            equity += float(source["pnl"])
            source["equity"] = round(equity, 2)
            parent = event_ids[LIFECYCLE[offset - 1]] if offset else ""
            detail = f"{action} {source['symbol']}: {reason}" if kind == "decision" else f"Demo cycle {cycle:03d}: retained {kind} record for {source['symbol']}."
            source.update({
                "kind": kind,
                "event_id": event_ids[kind],
                "parent_id": parent,
                "available_at": source["timestamp"],
                "decision_timestamp": source["timestamp"] if kind == "decision" else "",
                "strategy_id": "demo-mixed-fundamental-alpha" if kind == "decision" else "",
                "strategy_version": "2025.08-demo" if kind == "decision" else "",
                "model_version": "fundamental-ranker-2.1" if kind == "decision" else "",
                "feature_snapshot_id": f"features-{cycle:03d}" if kind == "decision" else "",
                "fill_quantity": str(traded_quantity) if kind == "fill" else "",
                "position_quantity": str(position_after) if kind == "position" else "",
                "detail": detail,
            })
            rows.append(source)
    return rows


if __name__ == "__main__":
    rows = build_rows()
    with OUTPUT.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows)} rows to {OUTPUT}")
