import http.client
import json
import threading
import unittest
from http.server import ThreadingHTTPServer

from server import Handler


class AttributionApiTests(unittest.TestCase):
    def setUp(self):
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.httpd.shutdown()
        self.thread.join()
        self.httpd.server_close()

    def test_attribution_endpoint_returns_reconciled_waterfall(self):
        rows = [{"pnl": -100, "selection_pnl": -60, "exposure_pnl": -20, "execution_pnl": -15, "data_quality_pnl": -5}]
        connection = http.client.HTTPConnection("127.0.0.1", self.httpd.server_port, timeout=5)
        connection.request("POST", "/api/incident-bundle/attribution", json.dumps({"rows": rows}), {"Content-Type": "application/json"})
        response = connection.getresponse()
        payload = json.loads(response.read())

        self.assertEqual(response.status, 200)
        self.assertEqual(payload["attribution"]["components"]["selection"], -60.0)
        self.assertTrue(payload["attribution"]["reconciled"])


if __name__ == "__main__":
    unittest.main()
