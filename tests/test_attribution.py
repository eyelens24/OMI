import unittest

from attribution import AttributionValidationError, attribute_pnl


class AttributionTests(unittest.TestCase):
    def test_returns_a_reconciled_waterfall_for_explicit_components(self):
        result = attribute_pnl([
            {"pnl": -100.0, "selection_pnl": -60.0, "exposure_pnl": -20.0, "execution_pnl": -15.0, "data_quality_pnl": -5.0},
            {"pnl": 40.0, "selection_pnl": 25.0, "exposure_pnl": 10.0, "execution_pnl": 3.0, "data_quality_pnl": 2.0},
        ])

        self.assertEqual(result["total_pnl"], -60.0)
        self.assertEqual(result["components"]["selection"], -35.0)
        self.assertEqual(result["components"]["execution"], -12.0)
        self.assertEqual(result["unexplained_pnl"], 0.0)
        self.assertTrue(result["reconciled"])

    def test_rejects_component_totals_that_do_not_reconcile(self):
        with self.assertRaisesRegex(AttributionValidationError, "do not reconcile"):
            attribute_pnl([
                {"pnl": -100.0, "selection_pnl": -20.0, "exposure_pnl": -20.0, "execution_pnl": -20.0, "data_quality_pnl": -20.0},
            ])


if __name__ == "__main__":
    unittest.main()
