import unittest
from investigation_graph import build_investigation_graph

class DynamicGraphTests(unittest.TestCase):
    def test_graph_uses_snapshot_analysis_route_not_fixed_template(self):
        records = [{"timestamp": "2026-08-21T09:30:00+00:00", "pnl": -1}]
        analysis = {"explanation_blocks": [{"stage": "Observed", "title": "Earnings estimate cuts", "copy": "Measured", "detail": "r=0.8"}]}
        graph = build_investigation_graph(records, analysis)
        self.assertIn("Earnings estimate cuts", [node["label"] for node in graph["nodes"]])

if __name__ == "__main__": unittest.main()
