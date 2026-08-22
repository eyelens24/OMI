import unittest
from pathlib import Path


class InvestigationGraphUiTests(unittest.TestCase):
    def test_ui_mounts_interactive_graph_and_replay_controls(self):
        root = Path(__file__).resolve().parents[1]
        html = (root / "index.html").read_text(encoding="utf-8")
        js = (root / "app.js").read_text(encoding="utf-8")
        self.assertIn('id="investigationGraph"', html)
        self.assertIn('id="replayScrubber"', html)
        self.assertIn('/api/investigation/graph', js)
        self.assertIn('renderInvestigationGraph', js)

if __name__ == "__main__": unittest.main()
