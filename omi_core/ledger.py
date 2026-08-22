"""Typed, local-only evidence contract for replayable decision-to-P&L incidents."""

EVIDENCE_STATUSES = {"supported", "missing", "contradicted", "time_invalid", "inferred"}
LIFECYCLE = ("observation", "decision", "target", "fill", "position", "pnl")


def assess_lifecycle(events):
    """Build a deterministic evidence ledger; never turn a missing link into proof."""
    by_type = {kind: [] for kind in LIFECYCLE}
    for event in events:
        if event.get("kind") in by_type:
            by_type[event["kind"]].append(event)
    steps, previous_ids = [], set()
    for kind in LIFECYCLE:
        rows = by_type[kind]
        if not rows:
            steps.append({"kind": kind, "status": "missing", "detail": f"No {kind} evidence supplied."})
            continue
        row = sorted(rows, key=lambda item: str(item.get("timestamp", "")))[0]
        status = "supported"
        if kind != "observation" and row.get("parent_id") and str(row["parent_id"]) not in previous_ids:
            status = "contradicted"
        if row.get("available_at") and row.get("timestamp") and str(row["available_at"]) > str(row["timestamp"]):
            status = "time_invalid"
        steps.append({"kind": kind, "status": status, "event_id": row.get("event_id"), "detail": row.get("detail", f"{kind} evidence recorded.")})
        previous_ids = {str(item["event_id"]) for item in rows if item.get("event_id")}
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
