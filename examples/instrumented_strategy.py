"""Runnable example: attach an unfamiliar strategy to Doctor Quant without changing its output."""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys

# Allow this example to run directly from the repository root or this folder.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from doctorquant_core import CompositeSink, HttpSink, JsonlSink, MemorySink, StrategyRecorder


def build_demo(*, server_url=None, output_path=None, start=None):
    memory = MemorySink()
    sinks = [memory]
    if server_url:
        sinks.append(HttpSink(server_url))
    if output_path:
        sinks.append(JsonlSink(output_path))

    recorder = StrategyRecorder(
        "unfamiliar_rsi_regime_v1",
        strategy_version="example-git:8d91c2a",
        parameters={"buy_below": 35, "sell_above": 65, "lot_size": 50},
        sink=CompositeSink(*sinks),
    )
    position = 0

    @recorder.instrument()
    def trading_algorithm(market):
        """This function knows nothing about Doctor Quant and returns its normal result."""
        current = int(market["current_position"])
        rsi = float(market["rsi_14"])
        regime = market["macro_regime"]
        liquid = float(market["liquidity_score"]) >= .5
        if rsi < 35 and regime == "risk_on" and liquid:
            return {"action": "BUY", "target_quantity": current + 50, "decision_reason": "RSI was oversold while regime and liquidity checks passed."}
        if rsi > 65 and current > 0:
            return {"action": "SELL", "target_quantity": max(0, current - 50), "decision_reason": "RSI was overbought, so the strategy reduced its position."}
        return {"action": "HOLD", "target_quantity": current, "decision_reason": "No buy or sell threshold was crossed."}

    first_time = start or datetime.now(timezone.utc).replace(second=0, microsecond=0)
    for index in range(60):
        decision_time = first_time + timedelta(minutes=index)
        rsi_pattern = (28, 42, 71, 50, 31, 68)
        market = {
            "symbol": "AAPL",
            "timestamp": decision_time.isoformat(),
            "available_at": (decision_time - timedelta(seconds=2)).isoformat(),
            "current_position": position,
            "rsi_14": rsi_pattern[index % len(rsi_pattern)],
            "macro_regime": "risk_on" if index % 9 != 8 else "risk_off",
            "liquidity_score": round(.45 + (index % 5) * .12, 2),
            "unused_vendor_debug_field": 10_000 + index,
        }
        result = trading_algorithm(market)
        receipt = recorder.latest_receipt("AAPL")
        target = int(result["target_quantity"])
        traded = target - position
        price = round(185 + index * .08, 2)
        position = target
        receipt.record_fill(quantity=traded, price=price, timestamp=decision_time + timedelta(seconds=1))
        receipt.record_position(quantity=position, timestamp=decision_time + timedelta(seconds=2))
        receipt.record_pnl(
            pnl=round(position * ((index % 7) - 3) * .015, 2),
            timestamp=decision_time + timedelta(seconds=3),
            market_price=price,
        )
    return recorder, memory


def main():
    parser = argparse.ArgumentParser(description="Record a synthetic unfamiliar strategy with Doctor Quant.")
    parser.add_argument("--server", help="Running Doctor Quant URL, for example http://127.0.0.1:8000")
    parser.add_argument("--output", help="Optional append-only JSONL evidence file")
    args = parser.parse_args()
    recorder, memory = build_demo(server_url=args.server, output_path=args.output)
    print(f"Captured {len(memory.events)} immutable events for {recorder.strategy_id}.")
    if args.server:
        print("In Doctor Quant, click 'Open latest recorded strategy'.")
    if args.output:
        print(f"Appended JSONL evidence to {args.output}.")


if __name__ == "__main__":
    main()
