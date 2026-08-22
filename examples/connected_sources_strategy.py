"""Example of merging unrelated data APIs and broker fields into one OMI receipt."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import argparse
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from omi_core import CallableConnector, ConnectorHub, ExecutionAdapter, FieldMapper, HttpSink, StrategyRecorder


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--server", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    now = datetime.now(timezone.utc).replace(microsecond=0)

    # These callables stand in for any vendor SDK. FieldMapper converts each
    # vendor's vocabulary into the names expected by this strategy.
    market_api = CallableConnector(
        "market-data-sdk",
        lambda **_: {"observed": (now - timedelta(seconds=4)).isoformat(), "published": (now - timedelta(seconds=2)).isoformat(), "indicators": {"relativeStrength14": 29.4}},
        version="vendor-market-v8",
        observed_at_field="observed",
        available_at_field="published",
        mapper=FieldMapper({"rsi_14": "indicators.relativeStrength14"}),
    )
    risk_api = CallableConnector(
        "portfolio-risk-sdk",
        lambda **_: {"timestamp": (now - timedelta(seconds=1)).isoformat(), "state": {"regimeName": "normal", "capacityRemaining": 0.72}},
        version="risk-policy-v3",
        mapper=FieldMapper({"risk_regime": "state.regimeName", "capacity_remaining": "state.capacityRemaining"}),
    )
    snapshot = ConnectorHub().add(market_api).add(risk_api).snapshot(decision_time=now, symbol="AAPL")

    recorder = StrategyRecorder("multi_source_strategy", strategy_version="example-v1", sink=HttpSink(args.server))

    def decide(inputs):
        if inputs["rsi_14"] < 35 and inputs["risk_regime"] == "normal" and inputs["capacity_remaining"] > .5:
            return {"action": "BUY", "target_quantity": 75, "decision_reason": "Oversold RSI passed portfolio risk and capacity checks."}
        return {"action": "HOLD", "target_quantity": 0, "decision_reason": "Connected inputs did not permit a trade."}

    receipt = recorder.capture_connected_decision(decide, snapshot)

    # A broker with completely different field names is normalized separately.
    broker = ExecutionAdapter(timestamp="eventTime", fill_quantity="filledQty", fill_price="avgPx", position_quantity="netPosition", pnl="netPL")
    broker.record_fill(receipt, {"eventTime": (now + timedelta(seconds=1)).isoformat(), "filledQty": 75, "avgPx": 229.14, "brokerOrderId": "example-1"})
    broker.record_position(receipt, {"eventTime": (now + timedelta(seconds=2)).isoformat(), "netPosition": 75, "account": "paper"})
    broker.record_pnl(receipt, {"eventTime": (now + timedelta(seconds=3)).isoformat(), "netPL": -12.5, "currency": "USD"})
    print("Recorded one multi-source decision. Click 'Open latest recorded strategy' in OMI.")


if __name__ == "__main__":
    main()
