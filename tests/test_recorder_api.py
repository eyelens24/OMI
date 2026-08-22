import json
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from urllib.request import urlopen

import server
from doctorquant_core.recorder import HttpSink, StrategyRecorder
from storage import InvestigationStore


class RecorderApiTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.original_store = server.STORE
        server.STORE = InvestigationStore(f"{self.directory.name}/recorder.db")
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.httpd.server_port}"

    def tearDown(self):
        self.httpd.shutdown()
        self.thread.join()
        self.httpd.server_close()
        server.STORE = self.original_store
        self.directory.cleanup()

    def get_json(self, path):
        with urlopen(self.base_url + path, timeout=5) as response:
            return response.status, json.loads(response.read())

    def test_http_recorder_can_be_reopened_as_dashboard_evidence(self):
        recorder = StrategyRecorder("connected.strategy", sink=HttpSink(self.base_url))
        receipt = recorder.capture_decision(
            lambda features: {"action": "BUY", "decision_reason": "Custom score passed.", "target_quantity": 25, "score": features["custom_score"]},
            {"custom_score": .91, "unused": 4},
            symbol="ABC",
            timestamp="2026-08-22T09:30:00Z",
        )
        receipt.record_fill(quantity=25, price=10, timestamp="2026-08-22T09:30:01Z")
        receipt.record_position(quantity=25, timestamp="2026-08-22T09:30:02Z")
        receipt.record_pnl(pnl=12, timestamp="2026-08-22T09:30:03Z")

        status, strategies = self.get_json("/api/flight-recorder/strategies")
        self.assertEqual(status, 200)
        self.assertEqual(strategies["strategies"][0]["strategy_id"], "connected.strategy")
        status, evidence = self.get_json("/api/flight-recorder/evidence?strategy_id=connected.strategy")
        self.assertEqual(status, 200)
        self.assertEqual([step["status"] for step in evidence["ledger"]["steps"]], ["supported"] * 6)
        self.assertEqual(evidence["ai_forensics"][0]["known"]["inputs"]["custom_score"], .91)
        self.assertEqual(evidence["outcome_records"][0]["position_quantity"], 25)


if __name__ == "__main__":
    unittest.main()
