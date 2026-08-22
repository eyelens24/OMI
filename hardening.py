"""Local-only forensic hardening primitives; never route, trade, or mutate sources."""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import datetime, timezone

BOUNDARY = "local-only/read-only"


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def source_hash(value):
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def adapt_read_only_bundle(bundle):
    """Describe imported evidence without changing it or contacting any provider."""
    if not isinstance(bundle, dict):
        raise ValueError("Read-only adapter requires an object bundle")
    tables = bundle.get("tables", {})
    if not isinstance(tables, dict):
        raise ValueError("Read-only adapter requires tables object")
    return {
        "mode": "read-only",
        "adapter": "incident-bundle/v1",
        "lineage": {
            "source_hash": source_hash(bundle),
            "table_counts": {name: len(rows) if isinstance(rows, list) else 0 for name, rows in sorted(tables.items())},
            "imported_at": "not-recorded-by-adapter",
        },
    }


def reconcile_lifecycle(lifecycle):
    """Gate forensic claims on an explicitly linked decision→P&L evidence chain."""
    if not isinstance(lifecycle, dict):
        raise ValueError("Reconciliation requires an object of lifecycle tables")
    chain = (("decisions", None, "event_id"), ("targets", "decision_id", "event_id"), ("fills", "target_id", "event_id"), ("positions", "fill_id", "event_id"), ("pnl", "position_id", "event_id"))
    known, gaps, counts = set(), [], {}
    for table, parent_field, identity in chain:
        rows = lifecycle.get(table) or []
        if not isinstance(rows, list):
            raise ValueError(f"{table} must be a list")
        counts[table] = len(rows)
        if not rows:
            gaps.append(f"missing {table}")
            continue
        ids = set()
        for row in rows:
            if not isinstance(row, dict) or not row.get(identity):
                gaps.append(f"{table} row missing {identity}")
                continue
            if parent_field and row.get(parent_field) not in known:
                gaps.append(f"{table} row has no linked {parent_field}")
            ids.add(str(row[identity]))
        known = ids
    return {"reconciled": not gaps, "counts": counts, "gaps": sorted(set(gaps)), "gate": "decision→target→fill→position→P&L", "limitation": "Linkage verifies supplied evidence structure, not broker or market truth."}


def bounded_counterfactuals(rows):
    """Show additive-component sensitivity only when explicit components exist."""
    if not isinstance(rows, list) or not rows:
        return []
    cards = []
    for field, label in (("selection_pnl", "Selection component removed"), ("exposure_pnl", "Exposure component removed"), ("execution_pnl", "Execution component removed"), ("data_quality_pnl", "Data-quality component removed")):
        values = []
        total = 0.0
        for row in rows:
            try:
                total += float(row.get("pnl", 0.0))
                if field not in row:
                    values = []
                    break
                values.append(float(row[field]))
            except (TypeError, ValueError):
                values = []
                break
        if values and any(values):
            component = round(sum(values), 2)
            cards.append({"id": field, "title": label, "observed_pnl": round(total, 2), "bounded_delta": round(-component, 2), "counterfactual_pnl": round(total - component, 2), "bounded": True, "limitation": "Sensitivity of explicit additive accounting component only; not causal proof and not a trading recommendation."})
    return cards


def make_reproducibility_receipt(snapshot_id, summary, lineage=None):
    if not snapshot_id:
        raise ValueError("Reproducibility receipt requires snapshot_id")
    payload = {"snapshot_id": snapshot_id, "summary": summary or {}, "lineage": lineage or {}, "boundary": BOUNDARY, "schema": "doctorquant-reproducibility/v1"}
    return {**payload, "receipt_id": source_hash(payload)[:20], "generated_at": datetime.now(timezone.utc).isoformat(), "limitations": ["Receipt fingerprints supplied local evidence and deterministic metadata.", "It does not establish production accuracy, causality, broker truth, or permission to trade."]}


def incident_command(records, label, snapshot, recent=None):
    pnl = sum(float(row.get("pnl", 0) or 0) for row in records)
    severe = min(records, key=lambda row: float(row.get("pnl", 0) or 0), default={})
    return {"boundary": BOUNDARY, "incident": {"label": label or "Local incident", "snapshot_id": snapshot["snapshot_id"], "records": len(records), "total_pnl": round(pnl, 2), "worst_timestamp": severe.get("timestamp"), "worst_pnl": severe.get("pnl")}, "recent_incidents": recent or [], "commander_note": "Triage only supplied local evidence. No broker, order, or account action is available."}
