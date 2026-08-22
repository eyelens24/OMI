import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from omi_core.ai_forensics import assess_ai_decision
from omi_core.connectors import CallableConnector, ConnectorHub, FieldMapper, FileConnector, HttpJsonConnector
from omi_core.recorder import StrategyRecorder


class FakeResponse:
    status = 200

    def __init__(self, payload):
        self.payload = json.dumps(payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return self.payload


class ConnectorTests(unittest.TestCase):
    def test_merges_unfamiliar_callable_sources_with_field_provenance(self):
        market = CallableConnector(
            "market-api",
            lambda **_: {"published": "2026-08-22T09:29:58Z", "seen": "2026-08-22T09:29:57Z", "payload": {"rsi": 31, "unused": 9}},
            version="market-v3",
            observed_at_field="seen",
            available_at_field="published",
            mapper=FieldMapper({"rsi_14": "payload.rsi", "unused_market_value": "payload.unused"}),
        )
        risk = CallableConnector(
            "risk-sdk",
            lambda **_: {"timestamp": "2026-08-22T09:29:59Z", "available_at": "2026-08-22T09:29:59Z", "regime": "normal"},
            mapper=FieldMapper({"risk_regime": "regime"}),
        )
        snapshot = ConnectorHub().add(market).add(risk).snapshot(decision_time="2026-08-22T09:30:00Z", symbol="AAPL")

        self.assertEqual(snapshot["rsi_14"], 31)
        self.assertEqual(snapshot.provenance["rsi_14"]["source_id"], "market-api")
        self.assertEqual(snapshot.provenance["risk_regime"]["source_id"], "risk-sdk")

        recorder = StrategyRecorder("connected.inputs")
        receipt = recorder.capture_connected_decision(
            lambda values: {"action": "BUY", "target_quantity": 10, "decision_reason": "RSI passed.", "score": values["rsi_14"]},
            snapshot,
        )
        decision = next(event for event in receipt.events if event["kind"] == "decision")
        self.assertEqual(decision["feature_values"], {"rsi_14": 31})
        self.assertEqual(set(decision["input_provenance"]), {"rsi_14"})
        self.assertEqual(assess_ai_decision(decision)["known"]["sources"]["rsi_14"]["source_id"], "market-api")

    def test_rejects_future_sources_and_unmapped_collisions(self):
        future = CallableConnector("future", lambda **_: {"timestamp": "2026-08-22T09:31:00Z", "available_at": "2026-08-22T09:31:00Z", "score": 1})
        with self.assertRaisesRegex(ValueError, "after the decision"):
            ConnectorHub().add(future).snapshot(decision_time="2026-08-22T09:30:00Z")

        first = CallableConnector("one", lambda **_: {"timestamp": "2026-08-22T09:29:00Z", "score": 1}, mapper=FieldMapper({"score": "score"}))
        second = CallableConnector("two", lambda **_: {"timestamp": "2026-08-22T09:29:00Z", "score": 2}, mapper=FieldMapper({"score": "score"}))
        with self.assertRaisesRegex(ValueError, "both produced"):
            ConnectorHub().add(first).add(second).snapshot(decision_time="2026-08-22T09:30:00Z")
        prefixed = ConnectorHub().add(first, prefix="first").add(second, prefix="second").snapshot(decision_time="2026-08-22T09:30:00Z")
        self.assertEqual(prefixed.values, {"first.score": 1, "second.score": 2})

    def test_reads_csv_as_of_without_future_rows(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "features.csv"
            path.write_text("timestamp,available_at,symbol,value\n2026-08-22T09:29:00Z,2026-08-22T09:29:30Z,AAPL,4\n2026-08-22T09:31:00Z,2026-08-22T09:31:30Z,AAPL,9\n")
            connector = FileConnector("feature-file", path, mapper=FieldMapper({"custom_value": "value"}, {"custom_value": int}))
            envelope = connector.read(symbol="AAPL", as_of="2026-08-22T09:30:00Z")
            self.assertEqual(envelope.values["custom_value"], 4)
            self.assertEqual(envelope.available_at, "2026-08-22T09:29:30Z")

    def test_http_connector_is_get_only_and_selects_nested_json(self):
        connector = HttpJsonConnector(
            "vendor-http",
            "https://data.example.test/latest",
            headers={"Authorization": "Bearer secret"},
            selector="result",
            query_builder=lambda symbol, as_of, **_: {"ticker": symbol, "at": as_of},
            mapper=FieldMapper({"sentiment_score": "metrics.sentiment"}),
        )
        payload = {"result": {"timestamp": "2026-08-22T09:29:00Z", "available_at": "2026-08-22T09:29:30Z", "metrics": {"sentiment": .61}}}
        with patch("omi_core.connectors.urlopen", return_value=FakeResponse(payload)) as opened:
            envelope = connector.read(symbol="AAPL", as_of="2026-08-22T09:30:00Z")
        request = opened.call_args.args[0]
        self.assertEqual(request.method, "GET")
        self.assertIn("ticker=AAPL", request.full_url)
        self.assertEqual(envelope.values["sentiment_score"], .61)
        self.assertNotIn("secret", json.dumps(envelope.provenance()))


if __name__ == "__main__":
    unittest.main()
