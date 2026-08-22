import unittest
from evidence_ledger import assess_lifecycle

class EvidenceLedgerTests(unittest.TestCase):
    def test_marks_complete_linked_lifecycle_supported(self):
        events = [
            {"kind": "observation", "event_id": "o", "timestamp": "2026-01-01T09:00:00Z"},
            {"kind": "decision", "event_id": "d", "parent_id": "o", "timestamp": "2026-01-01T09:01:00Z"},
            {"kind": "target", "event_id": "t", "parent_id": "d", "timestamp": "2026-01-01T09:02:00Z"},
            {"kind": "fill", "event_id": "f", "parent_id": "t", "timestamp": "2026-01-01T09:03:00Z"},
            {"kind": "position", "event_id": "p", "parent_id": "f", "timestamp": "2026-01-01T09:04:00Z"},
            {"kind": "pnl", "event_id": "x", "parent_id": "p", "timestamp": "2026-01-01T09:05:00Z"},
        ]
        self.assertEqual([step["status"] for step in assess_lifecycle(events)], ["supported"] * 6)

    def test_flags_missing_and_time_invalid_evidence(self):
        steps = assess_lifecycle([{"kind": "observation", "event_id": "o", "timestamp": "2026-01-01T09:00:00Z", "available_at": "2026-01-01T09:01:00Z"}])
        self.assertEqual(steps[0]["status"], "time_invalid")
        self.assertEqual(steps[1]["status"], "missing")
