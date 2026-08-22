"""Deterministic checks of retained AI decision provenance and rationale claims."""

from .profiling import discover_indicator_fields

REQUIRED = ("model_version", "feature_snapshot_id", "decision_timestamp", "available_at", "action")
DECISION_SIGNALS = ("alpha_score", "expected_return", "information_coefficient", "rank_ic", "earnings_revision_pct", "revenue_growth_yoy")


def assess_ai_decision(decision):
    missing = [field for field in REQUIRED if not decision.get(field)]
    contradictions = []
    reasons = set(decision.get("reason_codes") or [])
    values = decision.get("feature_values") or {}
    revision = values.get("earnings_revision")
    if "positive_earnings_revision" in reasons and revision is not None and float(revision) <= 0:
        contradictions.append("positive_earnings_revision conflicts with retained earnings_revision input")
    if decision.get("available_at") and decision.get("decision_timestamp") and str(decision["available_at"]) > str(decision["decision_timestamp"]):
        contradictions.append("decision input was available after the decision timestamp")
    status = "contradicted" if contradictions else "missing" if missing else "supported"
    signals = {field: decision[field] for field in DECISION_SIGNALS if decision.get(field) not in (None, "")}
    known_inputs = {field: decision[field] for field in discover_indicator_fields([decision])}
    known_inputs.update(decision.get("feature_values") or {})
    input_details = {
        field: {"value": value, "available_at": decision.get("available_at")}
        for field, value in known_inputs.items()
    }
    return {
        "status": status,
        "decision_id": decision.get("event_id"),
        "timestamp": decision.get("decision_timestamp") or decision.get("timestamp"),
        "symbol": decision.get("symbol"),
        "action": decision.get("action"),
        "target_weight": decision.get("target_weight"),
        "decision_reason": decision.get("decision_reason"),
        "signals": signals,
        "known": {
            "model_version": decision.get("model_version"),
            "feature_snapshot_id": decision.get("feature_snapshot_id"),
            "available_at": decision.get("available_at"),
            "inputs": known_inputs,
            "input_details": input_details,
            "sources": decision.get("input_provenance") or {},
        },
        "missing": missing,
        "contradictions": contradictions,
        "receipt": {"model_version": decision.get("model_version"), "feature_snapshot_id": decision.get("feature_snapshot_id"), "reason_codes": decision.get("reason_codes") or []},
    }
