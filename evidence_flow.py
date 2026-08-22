"""Deterministic, evidence-labelled diagnostic flows for OMI."""


def build_evidence_flow(records, analysis):
    """Return a route for every incident; never silently turn a gap into proof."""
    supported = analysis.get("explanation_blocks") or []
    if supported:
        flow = []
        for block in supported:
            item = dict(block)
            item["support"] = item.get("support", "supported")
            flow.append(item)
        return flow

    pnl = (analysis.get("summary") or {}).get("pnl")
    if pnl is None:
        pnl = sum(float(row.get("pnl", 0) or 0) for row in records)
    latest = records[-1] if records else {}
    target = latest.get("target_position", latest.get("target_quantity", latest.get("target_weight")))
    filled = latest.get("fill_quantity", latest.get("actual_position", latest.get("actual_weight")))
    available = latest.get("available_at")
    market_return = latest.get("return", latest.get("market_return"))
    if target is not None and filled is not None and str(target) != str(filled):
        candidate = ("Target-to-fill translation gap", "Target and actual/fill fields differ in the retained record.", "Evidence required: stable target ID, order/fill IDs, and position reconciliation.")
    elif available is not None and latest.get("timestamp") is not None and str(available) < str(latest.get("timestamp")):
        candidate = ("Potential stale or delayed input", "The retained input availability time predates the decision-time record.", "Evidence required: vendor snapshot version, observed_at, available_at, and revision history.")
    elif market_return is not None and float(market_return) < -0.02:
        candidate = ("Market-regime move", "The retained market return is materially negative in this window.", "Evidence required: benchmark, factor, position exposure, and valuation records.")
    else:
        candidate = ("Decision, translation, execution, or market regime", "The retained fields cannot yet separate these layers.", "Evidence required: decision, target, fill, position, and point-in-time market records.")
    return [
        {"stage": "Observed outcome", "title": "Recorded incident P&L", "copy": f"The retained window records {pnl:,.2f} P&L.", "detail": "Observed accounting outcome.", "kind": "outcome", "support": "supported"},
        {"stage": "Candidate route", "title": candidate[0], "copy": candidate[1], "detail": candidate[2], "kind": "candidate", "support": "candidate"},
        {"stage": "Investigation outcome", "title": "Ranked hypothesis—not established cause", "copy": "Use the missing evidence list to confirm or reject the candidate route.", "detail": "No causal claim is made until the chain reconciles.", "kind": "outcome", "support": "gap"},
    ]
