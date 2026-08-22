import unittest
from evidence_flow import build_evidence_flow

class EvidenceFlowTests(unittest.TestCase):
    def test_retains_supported_explanation_blocks(self):
        flow = build_evidence_flow([{"timestamp": "2026-01-01T00:00:00Z", "pnl": -10}], {"explanation_blocks": [{"stage": "Observed", "title": "Stale input", "kind": "evidence"}]})
        self.assertEqual(flow[0]["title"], "Stale input")
        self.assertEqual(flow[0]["support"], "supported")

    def test_creates_labeled_candidate_route_when_no_supported_blocks_exist(self):
        flow = build_evidence_flow([{"timestamp": "2026-01-01T00:00:00Z", "pnl": -100, "return": -0.04}], {"summary": {"pnl": -100}})
        self.assertEqual(len(flow), 3)
        self.assertEqual(flow[0]["stage"], "Observed outcome")
        self.assertEqual(flow[1]["support"], "candidate")
        self.assertIn("evidence required", flow[1]["detail"].lower())

    def test_ranks_target_fill_gap_from_present_fields(self):
        flow = build_evidence_flow([{"timestamp": "2026-01-01T00:00:00Z", "pnl": -10, "target_quantity": 100, "fill_quantity": 80}], {"summary": {"pnl": -10}})
        self.assertEqual(flow[1]["title"], "Target-to-fill translation gap")

    def test_ranks_market_move_from_present_fields(self):
        flow = build_evidence_flow([{"timestamp": "2026-01-01T00:00:00Z", "pnl": -10, "market_return": -0.04}], {"summary": {"pnl": -10}})
        self.assertEqual(flow[1]["title"], "Market-regime move")
