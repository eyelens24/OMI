import http.client
import json
import threading
import unittest
from http.server import ThreadingHTTPServer

from server import Handler


class InvestigationGraphApiTests(unittest.TestCase):
    def setUp(self):
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.httpd.shutdown(); self.thread.join(); self.httpd.server_close()

    def test_graph_endpoint_returns_replay_and_evidence_nodes(self):
        records = [
            {"timestamp":"2026-08-21T09:42:00+00:00","symbol":"AAPL","pnl":-10,"action":"BUY","target_weight":0.05,"fundamental_age_days":2},
            {"timestamp":"2026-08-21T10:05:00+00:00","symbol":"AAPL","pnl":-100,"slippage_bps":30},
        ]
        conn = http.client.HTTPConnection("127.0.0.1", self.httpd.server_port, timeout=5)
        conn.request("POST", "/api/investigation/graph", json.dumps({"records":records}), {"Content-Type":"application/json"})
        response = conn.getresponse(); payload = json.loads(response.read())
        self.assertEqual(response.status, 200)
        self.assertEqual(len(payload["graph"]["timeline"]), 2)
        self.assertTrue(any(node["label"] == "Strategy P&L" for node in payload["graph"]["nodes"]))

if __name__ == "__main__": unittest.main()
