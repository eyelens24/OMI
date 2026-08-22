from datetime import datetime, timedelta, timezone
import http.client
import json
import threading
import unittest
from http.server import ThreadingHTTPServer

from hardening import adapt_read_only_bundle, reconcile_lifecycle, bounded_counterfactuals, make_reproducibility_receipt
from server import Handler


def rows(count=55):
    start = datetime(2026, 8, 21, 9, 0, tzinfo=timezone.utc)
    return [{"timestamp": (start + timedelta(minutes=index)).isoformat(), "pnl": -1.0 - index / 10, "return": -0.001 - index / 100000, "volatility": .2 + index / 1000, "volume_ratio": 1 + index / 1000, "spread_bps": 2 + index / 1000, "slippage_bps": 1 + index / 1000} for index in range(count)]


class HardeningUnitTests(unittest.TestCase):
    def test_read_only_adapter_emits_deterministic_lineage_without_actions(self):
        bundle = {"manifest": {"incident_id": "i-1"}, "tables": {"decisions": [{"event_id": "d-1"}], "pnl": [{"event_id": "p-1", "pnl": -10}]}}
        adapted = adapt_read_only_bundle(bundle)
        self.assertEqual(adapted["mode"], "read-only")
        self.assertIn("source_hash", adapted["lineage"])
        self.assertNotIn("actions", adapted)

    def test_reconciliation_gate_requires_a_complete_linked_lifecycle(self):
        lifecycle = {"decisions": [{"event_id": "d1"}], "targets": [{"event_id": "t1", "decision_id": "d1"}], "fills": [{"event_id": "f1", "target_id": "t1"}], "positions": [{"event_id": "x1", "fill_id": "f1"}], "pnl": [{"event_id": "p1", "position_id": "x1", "pnl": -3}]}
        self.assertTrue(reconcile_lifecycle(lifecycle)["reconciled"])
        lifecycle["pnl"][0]["position_id"] = "missing"
        self.assertFalse(reconcile_lifecycle(lifecycle)["reconciled"])

    def test_counterfactuals_are_bounded_and_labelled_not_causal(self):
        cards = bounded_counterfactuals([{"pnl": -10, "execution_pnl": -3, "selection_pnl": -7}])
        self.assertTrue(cards)
        self.assertTrue(all(card["bounded"] and "not causal" in card["limitation"].lower() for card in cards))

    def test_reproducibility_receipt_binds_snapshot_and_artifacts(self):
        receipt = make_reproducibility_receipt("snap-1", {"records": 55}, {"adapter": "bundle/v1"})
        self.assertEqual(receipt["snapshot_id"], "snap-1")
        self.assertIn("receipt_id", receipt)
        self.assertEqual(receipt["boundary"], "local-only/read-only")


class HardeningApiTests(unittest.TestCase):
    def setUp(self):
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.httpd.shutdown(); self.thread.join(); self.httpd.server_close()

    def post(self, path, payload):
        conn = http.client.HTTPConnection("127.0.0.1", self.httpd.server_port, timeout=10)
        conn.request("POST", path, json.dumps(payload), {"Content-Type": "application/json"})
        response = conn.getresponse()
        return response.status, json.loads(response.read())

    def test_replay_keeps_one_snapshot_identity_across_analysis_and_graph(self):
        status, result = self.post("/api/investigation/replay", {"records": rows(), "as_of": rows()[-1]["timestamp"], "source": "test"})
        self.assertEqual(status, 200)
        self.assertEqual(result["snapshot_id"], result["analysis"]["snapshot_id"])
        self.assertEqual(result["snapshot_id"], result["graph"]["snapshot_id"])

    def test_short_replay_still_returns_a_decision_receipt(self):
        short_rows = rows(3)
        status, result = self.post("/api/investigation/replay", {"records": short_rows, "as_of": short_rows[-1]["timestamp"], "source": "test"})

        self.assertEqual(status, 200)
        self.assertTrue(result["evidence_ready"])
        self.assertFalse(result["analysis_ready"])
        self.assertIn("ledger", result)

    def test_command_center_and_receipt_expose_local_read_only_forensics(self):
        status, command = self.post("/api/incident-command", {"records": rows(), "label": "test incident"})
        self.assertEqual(status, 200)
        self.assertEqual(command["boundary"], "local-only/read-only")
        self.assertIn("incident", command)
        status, receipt = self.post("/api/reproducibility-receipt", {"records": rows(), "as_of": rows()[-1]["timestamp"], "source": "test"})
        self.assertEqual(status, 200)
        self.assertEqual(receipt["boundary"], "local-only/read-only")
        self.assertIn("snapshot_id", receipt)


if __name__ == "__main__": unittest.main()
