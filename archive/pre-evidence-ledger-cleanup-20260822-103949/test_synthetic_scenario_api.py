import json
import threading
import unittest
from http.server import ThreadingHTTPServer
from urllib.request import urlopen
from server import Handler

class SyntheticScenarioApiTests(unittest.TestCase):
    def test_catalog_is_local_and_has_truth_labels(self):
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with urlopen(f'http://127.0.0.1:{server.server_port}/api/synthetic-scenarios') as response:
                payload = json.load(response)
            self.assertEqual([item['id'] for item in payload['scenarios']], ['stale-input', 'execution-gap', 'market-shock'])
            self.assertTrue(all(item['ground_truth'] for item in payload['scenarios']))
        finally:
            server.shutdown(); server.server_close(); thread.join()
