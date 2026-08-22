import unittest

from incident_bundle import BundleValidationError, validate_incident_bundle


VALID_BUNDLE = {
    "manifest": {
        "schema_version": "incident-bundle/v1",
        "incident_id": "incident-2026-08-21-aapl",
        "strategy_version": "mean-reversion-2.3.1",
        "parameter_hash": "abc123",
    },
    "tables": {
        "decisions": [{
            "event_id": "decision-1",
            "event_timestamp": "2026-08-21T14:00:00+00:00",
            "available_at": "2026-08-21T13:59:00+00:00",
            "symbol_id": "US0378331005",
            "action": "BUY",
            "target_weight": 0.05,
            "alpha_score": 0.72,
        }],
        "pnl": [{
            "event_id": "pnl-1",
            "event_timestamp": "2026-08-21T20:00:00+00:00",
            "symbol_id": "US0378331005",
            "pnl": -1250.0,
        }],
    },
}


class IncidentBundleValidationTests(unittest.TestCase):
    def test_valid_decision_and_pnl_bundle_is_assessable(self):
        receipt = validate_incident_bundle(VALID_BUNDLE)

        self.assertEqual(receipt["schema_version"], "incident-bundle/v1")
        self.assertFalse(receipt["assessment_blocked"])
        self.assertEqual(receipt["coverage"]["decision_evidence"], "complete")
        self.assertEqual(receipt["coverage"]["pnl_evidence"], "complete")

    def test_future_available_at_is_rejected_to_prevent_lookahead(self):
        bundle = {
            **VALID_BUNDLE,
            "tables": {
                **VALID_BUNDLE["tables"],
                "decisions": [{
                    **VALID_BUNDLE["tables"]["decisions"][0],
                    "available_at": "2026-08-21T14:01:00+00:00",
                }],
            },
        }

        with self.assertRaisesRegex(BundleValidationError, "available_at.*after event_timestamp"):
            validate_incident_bundle(bundle)

    def test_missing_execution_data_blocks_execution_attribution_not_diagnosis(self):
        receipt = validate_incident_bundle(VALID_BUNDLE)

        self.assertTrue(receipt["assessment_blocked_for"]["execution_attribution"])
        self.assertIn("fills", receipt["missing_tables"])


if __name__ == "__main__":
    unittest.main()
