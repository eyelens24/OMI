"""Deterministic P&L attribution for incident forensics."""


class AttributionValidationError(ValueError):
    pass


_COMPONENTS = {
    "selection": "selection_pnl",
    "exposure": "exposure_pnl",
    "execution": "execution_pnl",
    "data_quality": "data_quality_pnl",
}


def _number(row, field):
    try:
        return float(row.get(field, 0.0))
    except (TypeError, ValueError) as error:
        raise AttributionValidationError(f"{field} must be numeric") from error


def attribute_pnl(rows, tolerance=0.01):
    """Return a reconciled, additive waterfall from explicitly supplied fields."""
    if not isinstance(rows, list) or not rows:
        raise AttributionValidationError("Attribution requires at least one P&L row")
    totals = {name: 0.0 for name in _COMPONENTS}
    total_pnl = 0.0
    for row in rows:
        if not isinstance(row, dict) or "pnl" not in row:
            raise AttributionValidationError("Each attribution row requires pnl")
        total_pnl += _number(row, "pnl")
        for name, field in _COMPONENTS.items():
            totals[name] += _number(row, field)
    total_pnl = round(total_pnl, 2)
    totals = {name: round(value, 2) for name, value in totals.items()}
    component_total = round(sum(totals.values()), 2)
    unexplained = round(total_pnl - component_total, 2)
    if abs(unexplained) > tolerance:
        raise AttributionValidationError(
            f"Attribution components do not reconcile to P&L (unexplained {unexplained:.2f})"
        )
    return {
        "total_pnl": total_pnl,
        "components": totals,
        "unexplained_pnl": unexplained,
        "reconciled": True,
        "method": "explicit-additive-components/v1",
    }
