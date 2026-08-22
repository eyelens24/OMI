"""Read-only detection of strategy fields and decision-time inputs."""

FIELD_GROUPS = {
    "action": ("action", "side", "signal", "decision"),
    "reason": ("decision_reason", "reason", "rationale", "reason_code"),
    "target": ("target_weight", "target_position", "target_quantity"),
    "execution": ("fill_quantity", "quantity", "fill_price"),
    "position": ("position_quantity", "position", "actual_position"),
    "model": ("model_version", "strategy_version", "feature_snapshot_id"),
    "pnl": ("pnl", "realized_pnl", "realised_pnl", "net_pnl"),
}
SIGNALS = ("alpha_score", "expected_return", "information_coefficient", "rank_ic", "earnings_revision_pct", "revenue_growth_yoy")
ACTION_MAP = {"BUY": "BUY", "B": "BUY", "LONG": "BUY", "SELL": "SELL", "S": "SELL", "SHORT": "SELL", "HOLD": "HOLD", "FLAT": "HOLD", "NONE": "HOLD"}

# These describe identity, actions, execution, positions, or outcomes. Everything
# else supplied on a strategy/observation row is treated as a candidate model
# input. This lets an imported strategy expose ten custom indicators without an
# OMI code change, while keeping post-decision results out of "what it knew".
NON_INPUT_FIELDS = {
    "timestamp", "available_at", "decision_timestamp", "kind", "event_type",
    "event_id", "parent_id", "decision_id", "target_id", "order_id", "fill_id",
    "position_id", "strategy_id", "strategy_version", "model_version",
    "feature_snapshot_id", "symbol", "ticker", "asset", "action", "side",
    "signal", "decision", "decision_reason", "reason", "rationale", "reason_code",
    "reason_codes", "detail", "source", "feature_values", "target_weight",
    "target_position", "target_quantity", "fill_quantity", "quantity",
    "fill_price", "position_quantity", "position", "actual_position", "pnl",
    "realized_pnl", "realised_pnl", "net_pnl", "equity", "fees", "venue",
    "implementation_shortfall", "slippage_bps", "weight_error_bps", "target_actual_weight_gap_bps",
    "input_hash", "model_hash", "code_hash", "parameter_hash", "raw_artifact_hash", "input_provenance",
}


def _fields(records):
    return {str(key).strip().lower(): key for row in records if isinstance(row, dict) for key in row}


def _present(value):
    return value is not None and str(value).strip() != ""


def discover_indicator_fields(records):
    """Return arbitrary retained input columns in stable source-column order."""
    discovered = []
    seen = set()
    for row in records:
        if not isinstance(row, dict):
            continue
        for field, value in row.items():
            normalised = str(field).strip().lower()
            if normalised in seen or normalised in NON_INPUT_FIELDS or normalised.endswith("_id"):
                continue
            if isinstance(value, (dict, list, tuple, set)) or not _present(value):
                continue
            seen.add(normalised)
            discovered.append(field)
    return discovered


def inspect_strategy(records):
    fields = _fields(records)
    detected = {name: next((fields[field] for field in choices if field in fields), None) for name, choices in FIELD_GROUPS.items()}
    signals = discover_indicator_fields(records)
    parts = []
    for name in ("action", "reason", "target", "execution", "position", "model", "pnl"):
        if detected[name]: parts.append(name)
    summary = f"Detected {', '.join(parts) if parts else 'P&L only'} fields and {len(signals)} decision input{'s' if len(signals) != 1 else ''} from the imported strategy data."
    return {"detected": detected, "signals": signals, "input_count": len(signals), "summary": summary}


def detected_decision(records):
    """Return the latest plainly recorded action without claiming typed provenance."""
    profile = inspect_strategy(records)
    action_field = profile["detected"]["action"]
    if not action_field:
        return None
    for index in range(len(records) - 1, -1, -1):
        row = records[index]
        raw = str(row.get(action_field, "")).strip().upper()
        action = ACTION_MAP.get(raw)
        if not action:
            continue
        reason_field = profile["detected"]["reason"]
        target_field = profile["detected"]["target"]
        decision_time = row.get("decision_timestamp") or row.get("timestamp")
        symbol = row.get("symbol")
        known_inputs, input_details = {}, {}
        # Walk backwards so each custom indicator is the newest value the
        # strategy could have seen, never a value recorded after the decision.
        for field in profile["signals"]:
            for candidate in reversed(records[:index + 1]):
                if symbol and candidate.get("symbol") not in (None, "", symbol):
                    continue
                available_at = candidate.get("available_at") or candidate.get("timestamp")
                if decision_time and available_at and str(available_at) > str(decision_time):
                    continue
                if _present(candidate.get(field)):
                    known_inputs[field] = candidate[field]
                    input_details[field] = {"value": candidate[field], "available_at": available_at}
                    break
        return {
            "status": "detected",
            "decision_id": row.get("event_id"),
            "source": f"Detected from imported {action_field} field",
            "timestamp": decision_time, "symbol": symbol, "action": action,
            "target_weight": row.get(target_field) if target_field else None,
            "decision_reason": row.get(reason_field) if reason_field else None,
            "signals": {field: known_inputs[field] for field in SIGNALS if field in known_inputs},
            "known": {
                "model_version": row.get(profile["detected"]["model"]) if profile["detected"]["model"] else None,
                "feature_snapshot_id": row.get("feature_snapshot_id"),
                "available_at": row.get("available_at") or decision_time,
                "inputs": known_inputs,
                "input_details": input_details,
            },
            "missing": [], "contradictions": [], "receipt": {"reason_codes": []},
        }
    return None
