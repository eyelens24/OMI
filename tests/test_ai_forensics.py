import unittest
from omi_core.ai_forensics import assess_ai_decision

class AiForensicsTests(unittest.TestCase):
    def test_reports_missing_provenance(self):
        result = assess_ai_decision({"event_id": "d1", "kind": "decision"})
        self.assertEqual(result["status"], "missing")
        self.assertIn("model_version", result["missing"])

    def test_flags_rationale_contradiction_against_input_snapshot(self):
        result = assess_ai_decision({
            "event_id": "d1", "kind": "decision", "model_version": "m1", "feature_snapshot_id": "f1",
            "decision_timestamp": "2026-01-01T09:00:00Z", "available_at": "2026-01-01T08:59:00Z",
            "action": "BUY", "target_weight": .05, "reason_codes": ["positive_earnings_revision"],
            "feature_values": {"earnings_revision": -0.12},
        })
        self.assertEqual(result["status"], "contradicted")
        self.assertIn("positive_earnings_revision", result["contradictions"][0])
