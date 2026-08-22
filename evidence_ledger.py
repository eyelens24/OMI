"""Compatibility import; canonical Evidence Ledger lives in doctorquant_core.ledger."""
from doctorquant_core.ledger import EVIDENCE_STATUSES, LIFECYCLE, assess_lifecycle, first_break

__all__ = ["EVIDENCE_STATUSES", "LIFECYCLE", "assess_lifecycle", "first_break"]
