import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class IncidentBundleUiTests(unittest.TestCase):
    def test_ui_exposes_a_json_incident_bundle_upload_path(self):
        html = (ROOT / "index.html").read_text(encoding="utf-8")
        javascript = (ROOT / "app.js").read_text(encoding="utf-8")

        self.assertIn('id="incidentBundleInput"', html)
        self.assertIn('id="uploadIncidentBundle"', html)
        self.assertIn('/api/incident-bundle/validate', javascript)
        self.assertIn('Evidence receipt', javascript)


if __name__ == "__main__":
    unittest.main()
