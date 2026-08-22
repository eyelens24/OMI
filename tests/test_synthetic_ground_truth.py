import unittest
from synthetic_ground_truth import scenario_catalog

class SyntheticGroundTruthTests(unittest.TestCase):
    def test_catalog_has_named_root_causes_and_complete_evidence_chain(self):
        for scenario in scenario_catalog():
            self.assertIn("ground_truth", scenario)
            self.assertIn("decision", scenario["evidence"])
            self.assertIn("target", scenario["evidence"])
            self.assertIn("fill", scenario["evidence"])
            self.assertIn("position", scenario["evidence"])
            self.assertIn("pnl", scenario["evidence"])

if __name__ == "__main__": unittest.main()
