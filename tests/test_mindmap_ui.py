import unittest
from pathlib import Path


class MindmapUiTests(unittest.TestCase):
    def test_graph_uses_readable_centered_causal_squares(self):
        root = Path(__file__).resolve().parents[1]
        javascript = (root / "app.js").read_text(encoding="utf-8")
        stylesheet = (root / "styles.css").read_text(encoding="utf-8")
        self.assertIn("renderCausalFlow", javascript)
        self.assertIn("causal-step", javascript)
        self.assertIn(".causal-flow", stylesheet)
        self.assertIn("justify-content:center", stylesheet)
        self.assertIn("min-width:100%", stylesheet)

if __name__ == "__main__": unittest.main()
