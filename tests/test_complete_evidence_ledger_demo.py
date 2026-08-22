import json
import unittest
from pathlib import Path

from doctorquant_core.ai_forensics import assess_ai_decision
from doctorquant_core.imports import validate_event_bundle
from doctorquant_core.ledger import ledger_for_records
from investigation_graph import reconstruct_as_of
from server import analyse, load_sample


class CompleteEvidenceLedgerDemoTests(unittest.TestCase):
    def test_complete_demo_reconciles_every_lifecycle_step(self):
        path = Path(__file__).resolve().parents[1] / "examples" / "complete-evidence-ledger.json"
        bundle = json.loads(path.read_text())
        imported = validate_event_bundle(bundle)
        ledger = ledger_for_records(imported["events"])
        decision = next(event for event in imported["events"] if event["kind"] == "decision")

        self.assertEqual(imported["accepted"], 6)
        self.assertFalse(imported["rejected"])
        self.assertEqual([step["status"] for step in ledger["steps"]], ["supported"] * 6)
        self.assertIsNone(ledger["first_break"])
        self.assertEqual(assess_ai_decision(decision)["status"], "supported")

    def test_full_product_csv_has_analysis_window_and_complete_ledger(self):
        records = load_sample("full-product")
        ledger = ledger_for_records(records)

        self.assertGreaterEqual(len(records), 50)
        self.assertTrue(all(record.get("pnl") not in (None, "") for record in records))
        self.assertEqual([step["status"] for step in ledger["steps"]], ["supported"] * 6)
        self.assertIn(ledger["steps"][1]["action"], {"BUY", "SELL", "HOLD"})
        self.assertTrue({"BUY", "SELL", "HOLD"}.issubset({row["action"] for row in records if row["kind"] == "decision"}))
        positions = [int(row["position_quantity"]) for row in records if row["kind"] == "position"]
        self.assertGreater(len(set(positions)), 2)
        self.assertTrue(any(int(row["fill_quantity"]) < 0 for row in records if row["kind"] == "fill"))

    def test_symbols_use_distinct_action_schedules_and_indicators(self):
        records = load_sample("full-product")
        decisions = [row for row in records if row["kind"] == "decision"]
        schedules = {
            symbol: tuple(row["action"] for row in decisions if row["symbol"] == symbol)
            for symbol in {row["symbol"] for row in decisions}
        }
        self.assertEqual(len(schedules), 5)
        self.assertEqual(len(set(schedules.values())), 5)
        expected_inputs = {
            "AAPL": "rsi_14", "MSFT": "momentum_20d_pct", "NVDA": "implied_volatility",
            "JPM": "net_interest_margin_trend", "XOM": "oil_momentum_20d_pct",
        }
        for symbol, field in expected_inputs.items():
            symbol_decisions = [row for row in decisions if row["symbol"] == symbol]
            self.assertTrue(all(row[field] not in (None, "") for row in symbol_decisions))
            other_fields = set(expected_inputs.values()) - {field}
            self.assertTrue(all(all(row[other] == "" for other in other_fields) for row in symbol_decisions))

    def test_full_product_replay_window_keeps_one_complete_lineage(self):
        records = load_sample("full-product")
        index = 250
        window = records[index - 159:index + 1]
        snapshot = reconstruct_as_of(window, records[index]["timestamp"])
        ledger = ledger_for_records(snapshot)

        self.assertEqual([step["status"] for step in ledger["steps"]], ["supported"] * 6)

    def test_full_product_analysis_response_is_json_serializable(self):
        result = analyse(load_sample("full-product"))

        json.dumps(result)
