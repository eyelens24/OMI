"""Typed, local-only evidence contract for replayable decision-to-P&L incidents."""

EVIDENCE_STATUSES = {"supported", "missing", "contradicted", "time_invalid", "inferred"}
LIFECYCLE = ("observation", "decision", "target", "fill", "position", "pnl")


def assess_lifecycle(events):
    """Build a deterministic evidence ledger; never turn a missing link into proof."""
    by_type = {kind: [] for kind in LIFECYCLE}
    for event in events:
        if event.get("kind") in by_type:
            by_type[event["kind"]].append(event)
    for rows in by_type.values():
        rows.sort(key=lambda item: str(item.get("timestamp", "")))

    # A replay window can begin in the middle of another event cycle. Select one
    # actual lineage backwards from its newest P&L record, instead of combining
    # the first observation from one cycle with the first decision from another.
    # If no P&L record exists, retain the deterministic earliest-record fallback.
    by_id = {str(row["event_id"]): row for rows in by_type.values() for row in rows if row.get("event_id")}
    selected = {}
    cursor = by_type["pnl"][-1] if by_type["pnl"] else None
    if cursor:
        selected["pnl"] = cursor
        for kind in reversed(LIFECYCLE[:-1]):
            parent = by_id.get(str(cursor.get("parent_id"))) if cursor.get("parent_id") else None
            if not parent or parent.get("kind") != kind:
                break
            selected[kind] = parent
            cursor = parent

    steps, previous_id = [], None
    for kind in LIFECYCLE:
        rows = by_type[kind]
        if not rows:
            steps.append({"kind": kind, "status": "missing", "detail": f"No {kind} evidence supplied."})
            continue
        row = selected.get(kind, rows[0])
        status = "supported"
        if kind != "observation" and row.get("parent_id") and str(row["parent_id"]) != previous_id:
            status = "contradicted"
        if row.get("available_at") and row.get("timestamp") and str(row["available_at"]) > str(row["timestamp"]):
            status = "time_invalid"
        steps.append({
            "kind": kind,
            "status": status,
            "event_id": row.get("event_id"),
            "action": row.get("action") if kind == "decision" else None,
            "symbol": row.get("symbol") if kind == "decision" else None,
            "target_weight": row.get("target_weight"),
            "target_quantity": row.get("target_quantity"),
            "quantity": row.get("quantity") or row.get("fill_quantity") or row.get("position_quantity"),
            "price": row.get("price"),
            "pnl": row.get("pnl"),
            "detail": row.get("detail", f"{kind} evidence recorded."),
        })
        previous_id = str(row["event_id"]) if row.get("event_id") else None
    return steps


def first_break(steps):
    """Return the earliest lifecycle defect with a compact reproducibility receipt."""
    for index, step in enumerate(steps):
        if step.get("status") != "supported":
            return {
                **step,
                "index": index,
                "receipt": {
                    "first_break_kind": step.get("kind"),
                    "status": step.get("status"),
                    "event_id": step.get("event_id"),
                    "detail": step.get("detail"),
                },
            }
    return None


def ledger_for_records(records):
    """Adapt supplied event records into a typed ledger without inventing links."""
    typed = [dict(row) for row in records if row.get("kind") in LIFECYCLE]
    if not typed and records:
        first, last = records[0], records[-1]
        typed = [
            {"kind": "observation", "event_id": first.get("event_id", "observation-row"), "timestamp": first.get("timestamp"), "detail": "Supplied incident observation."},
            {"kind": "pnl", "event_id": last.get("event_id", "pnl-row"), "timestamp": last.get("timestamp"), "detail": "Supplied P&L observation."},
        ]
    steps = assess_lifecycle(typed)
    return {"steps": steps, "first_break": first_break(steps)}
