import unittest
from pathlib import Path

class UnifiedEvidencePathTests(unittest.TestCase):
    def test_graph_panel_is_replaced_by_single_evidence_path_surface(self):
        root = Path(__file__).resolve().parents[1]
        html = (root / 'index.html').read_text(encoding='utf-8')
        self.assertIn('Evidence path', html)
        self.assertNotIn('Investigation graph', html)

if __name__ == '__main__': unittest.main()
