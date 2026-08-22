"""Deterministic checks of retained AI decision provenance and rationale claims."""

REQUIRED = ("model_version", "feature_snapshot_id", "decision_timestamp", "available_at", "action")


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
    return {"status": status, "decision_id": decision.get("event_id"), "missing": missing, "contradictions": contradictions, "receipt": {"model_version": decision.get("model_version"), "feature_snapshot_id": decision.get("feature_snapshot_id"), "reason_codes": decision.get("reason_codes") or []}}
