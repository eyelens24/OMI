import unittest
from doctorquant_core.ledger import assess_lifecycle, first_break

class FirstBreakTests(unittest.TestCase):
    def test_returns_first_non_supported_step_with_receipt(self):
        events = [
            {"kind": "observation", "event_id": "o", "timestamp": "2026-01-01T09:00:00Z"},
            {"kind": "decision", "event_id": "d", "parent_id": "o", "timestamp": "2026-01-01T09:01:00Z"},
            {"kind": "target", "event_id": "t", "parent_id": "bad", "timestamp": "2026-01-01T09:02:00Z"},
        ]
        finding = first_break(assess_lifecycle(events))
        self.assertEqual(finding["kind"], "target")
        self.assertEqual(finding["status"], "contradicted")
        self.assertIn("receipt", finding)

    def test_returns_none_for_fully_supported_lifecycle(self):
        events = []
        parent = None
        for index, kind in enumerate(("observation", "decision", "target", "fill", "position", "pnl")):
            event_id = str(index)
            events.append({"kind": kind, "event_id": event_id, "parent_id": parent, "timestamp": f"2026-01-01T09:0{index}:00Z"})
            parent = event_id
        self.assertIsNone(first_break(assess_lifecycle(events)))
