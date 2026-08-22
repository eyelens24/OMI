import unittest

from investigation_graph import build_investigation_graph


class InvestigationGraphTests(unittest.TestCase):
    def test_graph_contains_only_measured_causal_steps_in_time_order(self):
        records = [
            {"timestamp": "2026-08-21T09:30:00+00:00", "symbol": "AAPL", "pnl": 12, "fundamental_age_days": 0.1},
            {"timestamp": "2026-08-21T09:42:00+00:00", "symbol": "AAPL", "pnl": -10, "fundamental_age_days": 2.5, "action": "BUY", "target_weight": 0.05},
            {"timestamp": "2026-08-21T10:05:00+00:00", "symbol": "AAPL", "pnl": -1250, "slippage_bps": 31},
        ]
        result = build_investigation_graph(records, {"root_causes": [{"title": "Unused hypothesis"}]})

        self.assertEqual([node["id"] for node in result["nodes"]], ["stale-input", "decision", "execution", "pnl"])
        self.assertEqual([(edge["source"], edge["target"]) for edge in result["edges"]], [("stale-input", "decision"), ("decision", "execution"), ("execution", "pnl")])

if __name__ == "__main__": unittest.main()
