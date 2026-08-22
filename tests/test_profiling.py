import unittest

from doctorquant_core.profiling import detected_decision, inspect_strategy


class StrategyProfilingTests(unittest.TestCase):
    def test_detects_strategy_fields_and_latest_action(self):
        rows = [{"timestamp": "2026-01-01T09:00:00Z", "action": "BUY", "decision_reason": "Signal crossed threshold.", "alpha_score": .8, "target_weight": .05, "pnl": -10}]
        profile = inspect_strategy(rows)
        decision = detected_decision(rows)
        self.assertEqual(profile["detected"]["action"], "action")
        self.assertEqual(profile["signals"], ["alpha_score"])
        self.assertEqual(decision["action"], "BUY")
        self.assertEqual(decision["status"], "detected")
        self.assertEqual(decision["known"]["inputs"]["alpha_score"], .8)

    def test_discovers_custom_indicators_and_never_uses_future_values(self):
        rows = [
            {"timestamp": "2026-01-01T08:59:00Z", "symbol": "XYZ", "custom_momentum_14": .42, "market_regime": "risk_on"},
            {"timestamp": "2026-01-01T09:00:00Z", "symbol": "XYZ", "action": "BUY", "reason": "Momentum passed the threshold.", "position_quantity": 100},
            {"timestamp": "2026-01-01T09:01:00Z", "symbol": "XYZ", "custom_momentum_14": -.8, "market_regime": "risk_off"},
        ]

        profile = inspect_strategy(rows)
        decision = detected_decision(rows)

        self.assertIn("custom_momentum_14", profile["signals"])
        self.assertIn("market_regime", profile["signals"])
        self.assertEqual(decision["known"]["inputs"]["custom_momentum_14"], .42)
        self.assertEqual(decision["known"]["inputs"]["market_regime"], "risk_on")
        self.assertEqual(decision["known"]["input_details"]["custom_momentum_14"]["available_at"], "2026-01-01T08:59:00Z")
