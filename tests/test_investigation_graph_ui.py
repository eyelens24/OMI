import unittest
from pathlib import Path


class InvestigationGraphUiTests(unittest.TestCase):
    def test_ui_keeps_graph_infrastructure_without_exposing_a_second_replay_control(self):
        root = Path(__file__).resolve().parents[1]
        html = (root / "index.html").read_text(encoding="utf-8")
        js = (root / "app.js").read_text(encoding="utf-8")
        self.assertIn('id="investigationGraph"', html)
        self.assertIn('id="replayScrubber"', html)
        self.assertIn('/api/investigation/graph', js)
        self.assertIn('renderInvestigationGraph', js)
        self.assertNotIn('controls.append(moment, scrubber)', js)

if __name__ == "__main__": unittest.main()
