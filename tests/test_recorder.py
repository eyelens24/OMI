import json
import tempfile
import unittest
from pathlib import Path

from omi_core.ai_forensics import assess_ai_decision
from omi_core.ledger import ledger_for_records
from omi_core.recorder import ExecutionAdapter, HttpSink, JsonlSink, MemorySink, StrategyRecorder
from server import flight_events_to_evidence, normalise_flight_event, typed_events_to_outcome_records


def unfamiliar_strategy(features):
    momentum = float(features["custom_momentum_17"])
    regime = features["market_regime"]
    action = "BUY" if momentum > .5 and regime == "risk_on" else "HOLD"
    return {
        "action": action,
        "decision_reason": "Custom momentum passed the threshold." if action == "BUY" else "No threshold crossed.",
        "target_quantity": 120 if action == "BUY" else 0,
        "confidence": .77,
    }


class StrategyRecorderTests(unittest.TestCase):
    def test_captures_used_inputs_identity_and_complete_lifecycle(self):
        sink = MemorySink()
        recorder = StrategyRecorder("unfamiliar.v1", strategy_version="git:abc123", parameters={"threshold": .5}, sink=sink)
        receipt = recorder.capture_decision(
            unfamiliar_strategy,
            {"custom_momentum_17": .72, "market_regime": "risk_on", "unused_debug_value": 999},
            symbol="xyz",
            timestamp="2026-08-22T09:30:00Z",
            available_at="2026-08-22T09:29:58Z",
        )
        receipt.record_fill(quantity=120, price=42.5, timestamp="2026-08-22T09:30:01Z")
        receipt.record_position(quantity=120, timestamp="2026-08-22T09:30:02Z")
        receipt.record_pnl(pnl=-18.2, timestamp="2026-08-22T16:00:00Z")

        self.assertEqual(receipt.result["action"], "BUY")
        self.assertEqual([event["kind"] for event in sink.events], ["observation", "decision", "target", "fill", "position", "pnl"])
        self.assertEqual([step["status"] for step in ledger_for_records(sink.events)["steps"]], ["supported"] * 6)
        decision = sink.events[1]
        self.assertEqual(set(decision["feature_values"]), {"custom_momentum_17", "market_regime"})
        self.assertNotIn("unused_debug_value", decision["feature_values"])
        self.assertTrue(decision["model_hash"])
        self.assertTrue(decision["parameter_hash"])
        self.assertEqual(assess_ai_decision(decision)["status"], "supported")

    def test_decorator_preserves_result_and_exposes_latest_receipt(self):
        recorder = StrategyRecorder("decorated.strategy")

        @recorder.instrument()
        def decide(features):
            return {"action": "HOLD", "decision_reason": "Waiting.", "target_quantity": 10, "score": features["custom_score"]}

        result = decide({"symbol": "ABC", "timestamp": "2026-08-22T09:30:00Z", "custom_score": .4, "unused": 1})

        self.assertEqual(result["action"], "HOLD")
        receipt = recorder.latest_receipt("ABC")
        self.assertIsNotNone(receipt)
        self.assertEqual(receipt.result, result)
        decision = next(event for event in recorder.events if event["kind"] == "decision")
        self.assertEqual(decision["feature_values"], {"custom_score": .4})

    def test_rejects_lookahead_and_unlinked_execution(self):
        recorder = StrategyRecorder("safe.strategy")
        with self.assertRaisesRegex(ValueError, "after the decision"):
            recorder.capture_decision(
                unfamiliar_strategy,
                {"custom_momentum_17": .7, "market_regime": "risk_on"},
                symbol="XYZ",
                timestamp="2026-08-22T09:30:00Z",
                available_at="2026-08-22T09:31:00Z",
            )

        no_target = recorder.capture_decision(lambda _: "HOLD", {"score": 0}, symbol="XYZ", timestamp="2026-08-22T09:32:00Z")
        with self.assertRaisesRegex(ValueError, "did not record a target"):
            no_target.record_fill(quantity=0, price=1, timestamp="2026-08-22T09:32:01Z")

    def test_jsonl_and_http_payloads_use_the_existing_collector_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "evidence.jsonl"
            recorder = StrategyRecorder("file.strategy", sink=JsonlSink(path))
            recorder.capture_decision(lambda values: {"action": "BUY", "target_weight": .1, "score": values["score"]}, {"score": .8}, symbol="ABC", timestamp="2026-08-22T09:30:00Z")
            rows = [json.loads(line) for line in path.read_text().splitlines()]
            self.assertEqual([row["kind"] for row in rows], ["observation", "decision", "target"])

        flight = HttpSink._flight_event(rows[1])
        self.assertEqual(flight["event_type"], "strategy_decision")
        self.assertEqual(flight["data"]["kind"], "decision")
        self.assertEqual(flight["event_id"], rows[1]["event_id"])

        restored = flight_events_to_evidence([normalise_flight_event(HttpSink._flight_event(row)) for row in rows])
        self.assertEqual([row["kind"] for row in restored], ["observation", "decision", "target"])
        self.assertEqual(restored[1]["parent_id"], restored[0]["event_id"])

    def test_typed_evidence_builds_no_lookahead_outcome_rows(self):
        recorder = StrategyRecorder("analysis.strategy")
        receipt = recorder.capture_decision(unfamiliar_strategy, {"custom_momentum_17": .72, "market_regime": "risk_on"}, symbol="XYZ", timestamp="2026-08-22T09:30:00Z")
        receipt.record_fill(quantity=120, price=42.5, timestamp="2026-08-22T09:30:01Z")
        receipt.record_position(quantity=120, timestamp="2026-08-22T09:30:02Z")
        receipt.record_pnl(pnl=-18.2, timestamp="2026-08-22T16:00:00Z")

        rows = typed_events_to_outcome_records(recorder.events)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["action"], "BUY")
        self.assertEqual(rows[0]["position_quantity"], 120)
        self.assertEqual(rows[0]["custom_momentum_17"], .72)
        self.assertEqual(rows[0]["pnl"], -18.2)

    def test_maps_unfamiliar_broker_fields_without_changing_the_recorder(self):
        recorder = StrategyRecorder("broker.adapter")
        receipt = recorder.capture_decision(lambda _: {"action": "BUY", "target_quantity": 40}, {"factor_x": .8}, symbol="ABC", timestamp="2026-08-22T09:30:00Z")
        adapter = ExecutionAdapter(timestamp="eventTime", fill_quantity="filledQty", fill_price="avgPx", position_quantity="netPosition", pnl="netPL")

        adapter.record_fill(receipt, {"eventTime": "2026-08-22T09:30:01Z", "filledQty": 40, "avgPx": 12.5, "brokerOrderId": "B-7"})
        adapter.record_position(receipt, {"eventTime": "2026-08-22T09:30:02Z", "netPosition": 40, "account": "paper"})
        adapter.record_pnl(receipt, {"eventTime": "2026-08-22T16:00:00Z", "netPL": 18.0, "currency": "USD"})

        self.assertEqual([step["status"] for step in ledger_for_records(recorder.events)["steps"]], ["supported"] * 6)
        self.assertEqual(recorder.events[3]["brokerOrderId"], "B-7")


if __name__ == "__main__":
    unittest.main()
