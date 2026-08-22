"""Incident Bundle v1 validation for reproducible systematic-investing investigations."""
from datetime import datetime


class BundleValidationError(ValueError):
    """Raised when a bundle cannot support point-in-time investigation."""


SCHEMA_VERSION = "incident-bundle/v1"
REQUIRED_MANIFEST_FIELDS = ("schema_version", "incident_id", "strategy_version", "parameter_hash")


def _parse_timestamp(value, field_name):
    if not isinstance(value, str) or not value:
        raise BundleValidationError(f"{field_name} must be an ISO-8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise BundleValidationError(f"{field_name} must be an ISO-8601 timestamp") from error
    if parsed.tzinfo is None:
        raise BundleValidationError(f"{field_name} must include a timezone offset")
    return parsed


def _require_fields(row, table_name, fields):
    missing = [field for field in fields if field not in row or row[field] in (None, "")]
    if missing:
        raise BundleValidationError(f"{table_name} row is missing required fields: {', '.join(missing)}")


def validate_incident_bundle(bundle):
    """Validate the smallest useful forensic bundle and return an evidence receipt.

    A bundle must link point-in-time decision evidence to P&L. Missing fills do
    not invalidate a diagnosis, but explicitly block execution attribution.
    """
    if not isinstance(bundle, dict):
        raise BundleValidationError("Incident bundle must be an object")
    manifest = bundle.get("manifest")
    tables = bundle.get("tables")
    if not isinstance(manifest, dict) or not isinstance(tables, dict):
        raise BundleValidationError("Incident bundle requires manifest and tables objects")

    _require_fields(manifest, "manifest", REQUIRED_MANIFEST_FIELDS)
    if manifest["schema_version"] != SCHEMA_VERSION:
        raise BundleValidationError(f"Unsupported schema_version: {manifest['schema_version']}")

    decisions = tables.get("decisions")
    pnl_rows = tables.get("pnl")
    if not isinstance(decisions, list) or not decisions:
        raise BundleValidationError("Incident bundle requires at least one decisions row")
    if not isinstance(pnl_rows, list) or not pnl_rows:
        raise BundleValidationError("Incident bundle requires at least one pnl row")

    for decision in decisions:
        if not isinstance(decision, dict):
            raise BundleValidationError("decisions rows must be objects")
        _require_fields(
            decision,
            "decisions",
            ("event_id", "event_timestamp", "available_at", "symbol_id", "action", "target_weight", "alpha_score"),
        )
        event_timestamp = _parse_timestamp(decision["event_timestamp"], "decisions.event_timestamp")
        available_at = _parse_timestamp(decision["available_at"], "decisions.available_at")
        if available_at > event_timestamp:
            raise BundleValidationError("decisions.available_at cannot be after event_timestamp (lookahead evidence)")

    for pnl_row in pnl_rows:
        if not isinstance(pnl_row, dict):
            raise BundleValidationError("pnl rows must be objects")
        _require_fields(pnl_row, "pnl", ("event_id", "event_timestamp", "symbol_id", "pnl"))
        _parse_timestamp(pnl_row["event_timestamp"], "pnl.event_timestamp")
        try:
            float(pnl_row["pnl"])
        except (TypeError, ValueError) as error:
            raise BundleValidationError("pnl.pnl must be numeric") from error

    missing_tables = [name for name in ("fills", "positions", "market_data", "fundamentals", "data_lineage") if not tables.get(name)]
    coverage = {
        "decision_evidence": "complete",
        "pnl_evidence": "complete",
        "execution_evidence": "complete" if "fills" not in missing_tables else "missing",
        "portfolio_evidence": "complete" if "positions" not in missing_tables else "missing",
        "market_evidence": "complete" if "market_data" not in missing_tables else "missing",
        "fundamental_evidence": "complete" if "fundamentals" not in missing_tables else "missing",
        "data_lineage": "complete" if "data_lineage" not in missing_tables else "missing",
    }
    assessment_blocked_for = {
        "diagnosis": False,
        "execution_attribution": "fills" in missing_tables,
        "portfolio_attribution": "positions" in missing_tables,
        "market_attribution": "market_data" in missing_tables,
        "fundamental_attribution": "fundamentals" in missing_tables,
        "lineage_assessment": "data_lineage" in missing_tables,
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "incident_id": manifest["incident_id"],
        "assessment_blocked": assessment_blocked_for["diagnosis"],
        "assessment_blocked_for": assessment_blocked_for,
        "coverage": coverage,
        "missing_tables": missing_tables,
        "counts": {"decisions": len(decisions), "pnl": len(pnl_rows)},
    }
