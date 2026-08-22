"""Build a compact, inspectable evidence graph and point-in-time replay."""


def reconstruct_as_of(records, as_of):
    """Return only evidence that existed at or before the requested instant."""
    if not as_of:
        raise ValueError("Replay requires an as_of timestamp")
    return [row for row in sorted(records, key=lambda item: item.get("timestamp", "")) if row.get("timestamp", "") <= as_of]


def build_investigation_graph(records, analysis, snapshot=None):
    if not isinstance(records, list) or not records:
        raise ValueError("Investigation graph requires incident records")
    ordered = sorted(records, key=lambda row: row.get("timestamp", ""))
    nodes, edges = [], []

    def node(node_id, label, evidence_type, timestamp=None, detail=""):
        nodes.append({"id": node_id, "label": label, "evidence_type": evidence_type, "timestamp": timestamp, "detail": detail})

    blocks = analysis.get("explanation_blocks") or []
    if blocks:
        for index, block in enumerate(blocks):
            node(f"route-{index}", block.get("title", block.get("stage", "Observed evidence")), "measured", ordered[-1].get("timestamp"), block.get("detail", block.get("copy", "")))
        edges = [{"source": f"route-{index}", "target": f"route-{index + 1}", "kind": "measured"} for index in range(len(blocks) - 1)]
        edges.append({"source": f"route-{len(blocks) - 1}", "target": "pnl", "kind": "measured"})
        node("pnl", "Strategy P&L", "measured", ordered[-1].get("timestamp"), "Snapshot outcome")
        return {"nodes": nodes, "edges": edges, "timeline": [{"timestamp": row.get("timestamp"), "symbol": row.get("symbol"), "pnl": row.get("pnl")} for row in ordered], "snapshot_id": snapshot.get("snapshot_id") if snapshot else None, "evidence_semantics": "Snapshot-specific retained evidence route; arrows do not prove causation."}

    # The replay graph intentionally uses only recorded facts. Hypotheses remain
    # in the diagnosis panel; mixing them into this sequence can invert time.

    first_decision = next((row for row in ordered if row.get("action")), None)
    stale_record = next((row for row in ordered if float(row.get("fundamental_age_days", 0) or 0) >= 1), None)
    execution_record = next((row for row in ordered if row.get("slippage_bps") not in (None, "")), None)
    worst_record = min(ordered, key=lambda row: float(row.get("pnl", 0) or 0))

    if stale_record:
        node("stale-input", "Input freshness degraded", "measured", stale_record["timestamp"], f"Fundamental age: {stale_record['fundamental_age_days']} days")
    if first_decision:
        node("decision", "Strategy decision", "measured", first_decision["timestamp"], f"{first_decision.get('action')} target {first_decision.get('target_weight', 'unknown')}")
    if execution_record:
        node("execution", "Execution shortfall", "measured", execution_record["timestamp"], f"Slippage: {execution_record['slippage_bps']} bps")
    node("pnl", "Strategy P&L", "measured", worst_record["timestamp"], f"Worst mark: {worst_record.get('pnl')}")

    node_ids = {item["id"] for item in nodes}
    if "stale-input" in node_ids and "decision" in node_ids:
        edges.append({"source": "stale-input", "target": "decision", "kind": "measured"})
    if "decision" in node_ids and "execution" in node_ids:
        edges.append({"source": "decision", "target": "execution", "kind": "measured"})
    predecessor = "execution" if "execution" in node_ids else "decision" if "decision" in node_ids else "stale-input"
    if predecessor:
        edges.append({"source": predecessor, "target": "pnl", "kind": "measured"})

    timeline = [{
        "timestamp": row.get("timestamp"),
        "symbol": row.get("symbol"),
        "pnl": row.get("pnl"),
        "event": "decision" if row.get("action") else "execution" if row.get("slippage_bps") not in (None, "") else "observation",
        "known_fields": sorted(key for key, value in row.items() if value not in (None, "")),
    } for row in ordered]
    return {"nodes": nodes, "edges": edges, "timeline": timeline}
