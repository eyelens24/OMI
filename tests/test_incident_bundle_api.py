import http.client
import json
import threading
import unittest
from http.server import ThreadingHTTPServer

from server import Handler


BUNDLE = {
    "manifest": {
        "schema_version": "incident-bundle/v1",
        "incident_id": "api-smoke",
        "strategy_version": "test-v1",
        "parameter_hash": "hash",
    },
    "tables": {
        "decisions": [{
            "event_id": "d1", "event_timestamp": "2026-08-21T14:00:00+00:00",
            "available_at": "2026-08-21T13:59:00+00:00", "symbol_id": "US0378331005",
            "action": "BUY", "target_weight": 0.05, "alpha_score": 0.72,
        }],
        "pnl": [{
            "event_id": "p1", "event_timestamp": "2026-08-21T20:00:00+00:00",
            "symbol_id": "US0378331005", "pnl": -1250.0,
        }],
    },
}


class IncidentBundleApiTests(unittest.TestCase):
    def setUp(self):
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.httpd.shutdown()
        self.thread.join()
        self.httpd.server_close()

    def test_validate_endpoint_returns_evidence_receipt_without_persisting_incident(self):
        connection = http.client.HTTPConnection("127.0.0.1", self.httpd.server_port, timeout=5)
        connection.request(
            "POST", "/api/incident-bundle/validate", json.dumps(BUNDLE),
            {"Content-Type": "application/json"},
        )
        response = connection.getresponse()
        payload = json.loads(response.read())

        self.assertEqual(response.status, 200)
        self.assertEqual(payload["receipt"]["incident_id"], "api-smoke")
        self.assertTrue(payload["receipt"]["assessment_blocked_for"]["execution_attribution"])


if __name__ == "__main__":
    unittest.main()
