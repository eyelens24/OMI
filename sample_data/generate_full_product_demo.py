"""Generate Doctor Quant's one presentation CSV with independent per-symbol strategies."""
from __future__ import annotations

import csv
from datetime import datetime, timedelta, timezone
import math
from pathlib import Path


OUTPUT = Path(__file__).with_name("full_product_demo.csv")
LIFECYCLE = ("observation", "decision", "target", "fill", "position", "pnl")
COMMON_FIELDS = (
    "timestamp", "symbol", "price", "return", "pnl", "equity",
    "expected_pnl", "implementation_shortfall", "volatility", "volume_ratio",
    "spread_bps", "slippage_bps", "signal_strength", "news_risk",
)
STRATEGY_FIELDS = (
    "strategy_type", "rsi_14", "price_to_ma_20_pct", "momentum_20d_pct",
    "trend_strength", "implied_volatility", "volatility_limit",
    "net_interest_margin_trend", "loan_loss_risk", "oil_momentum_20d_pct",
    "inventory_surprise_pct",
)
DECISION_FIELDS = (
    "action", "decision_reason", "target_position", "target_quantity",
    "target_weight", "fill_quantity", "fill_price", "position_quantity",
)
EVIDENCE_FIELDS = (
    "kind", "event_id", "parent_id", "available_at", "decision_timestamp",
    "strategy_id", "strategy_version", "model_version", "feature_snapshot_id",
    "detail",
)
FIELDS = COMMON_FIELDS + STRATEGY_FIELDS + DECISION_FIELDS + EVIDENCE_FIELDS


STRATEGIES = {
    "AAPL": {
        "name": "RSI mean reversion", "model": "aapl-rsi-reversion-3.2", "quantity": 40,
        "actions": ("HOLD", "BUY", "HOLD", "BUY", "HOLD", "SELL", "HOLD", "SELL", "BUY", "HOLD", "HOLD", "SELL"),
        "primary": (48, 27, 32, 24, 39, 68, 57, 73, 29, 44, 51, 66),
    },
    "MSFT": {
        "name": "20-day momentum", "model": "msft-momentum-2.4", "quantity": 30,
        "actions": ("HOLD", "BUY", "HOLD", "BUY", "HOLD", "SELL", "HOLD", "BUY", "HOLD", "HOLD", "SELL", "HOLD"),
        "primary": (1.2, 3.8, 1.7, 4.7, 2.1, -2.6, -0.5, 3.6, 2.2, 1.3, -3.1, -0.8),
    },
    "NVDA": {
        "name": "Volatility-gated growth", "model": "nvda-volatility-gate-1.9", "quantity": 20,
        "actions": ("HOLD", "BUY", "HOLD", "SELL", "HOLD", "BUY", "SELL", "HOLD", "BUY", "HOLD", "SELL", "HOLD"),
        "primary": (.55, .38, .47, .78, .58, .41, .75, .61, .39, .52, .80, .57),
    },
    "JPM": {
        "name": "Bank fundamentals", "model": "jpm-bank-quality-4.1", "quantity": 50,
        "actions": ("HOLD", "HOLD", "BUY", "HOLD", "BUY", "HOLD", "HOLD", "SELL", "HOLD", "BUY", "HOLD", "SELL"),
        "primary": (.01, .02, .08, .04, .09, .03, .00, -.08, -.02, .07, .01, -.10),
    },
    "XOM": {
        "name": "Oil trend and inventories", "model": "xom-energy-trend-2.7", "quantity": 60,
        "actions": ("HOLD", "BUY", "HOLD", "HOLD", "SELL", "HOLD", "HOLD", "BUY", "HOLD", "SELL", "HOLD", "BUY"),
        "primary": (2, 8, 3, 1, -6, -2, 0, 7, 4, -7, -1, 8),
    },
}


def strategy_inputs(symbol: str, cycle: int) -> dict[str, object]:
    """Return only the indicators used by this symbol's synthetic strategy."""
    value = STRATEGIES[symbol]["primary"][cycle]
    inputs = {field: "" for field in STRATEGY_FIELDS}
    inputs["strategy_type"] = STRATEGIES[symbol]["name"]
    if symbol == "AAPL":
        inputs.update(rsi_14=value, price_to_ma_20_pct=round((50 - value) / 7, 2))
    elif symbol == "MSFT":
        inputs.update(momentum_20d_pct=value, trend_strength=round(abs(value) / 5, 2))
    elif symbol == "NVDA":
        inputs.update(implied_volatility=value, volatility_limit=.70)
    elif symbol == "JPM":
        inputs.update(net_interest_margin_trend=value, loan_loss_risk=round(.22 - value, 2))
    else:
        inputs.update(oil_momentum_20d_pct=value, inventory_surprise_pct=round(-value / 2, 2))
    return inputs


def decision_reason(symbol: str, action: str, inputs: dict[str, object]) -> str:
    if symbol == "AAPL":
        return f"{action}: RSI was {inputs['rsi_14']}; below 30 buys and above 65 sells while the middle range holds."
    if symbol == "MSFT":
        return f"{action}: 20-day momentum was {inputs['momentum_20d_pct']}%; above 3% buys and below -2% sells."
    if symbol == "NVDA":
        return f"{action}: implied volatility was {inputs['implied_volatility']}; low volatility permits exposure and above 0.70 exits it."
    if symbol == "JPM":
        return f"{action}: net-interest-margin trend was {inputs['net_interest_margin_trend']}; improving margins buy and sharp contraction sells."
    return f"{action}: 20-day oil momentum was {inputs['oil_momentum_20d_pct']}%; above 6% buys and below -5% sells."


def build_rows() -> list[dict[str, object]]:
    rows = []
    start = datetime(2025, 8, 18, 9, 30, tzinfo=timezone.utc)
    prices = {"AAPL": 225.0, "MSFT": 415.0, "NVDA": 135.0, "JPM": 218.0, "XOM": 112.0}
    positions = {symbol: 0 for symbol in STRATEGIES}
    equities = {symbol: 0.0 for symbol in STRATEGIES}

    for cycle in range(12):
        for symbol_index, (symbol, strategy) in enumerate(STRATEGIES.items()):
            action = strategy["actions"][cycle]
            quantity = strategy["quantity"]
            before = positions[symbol]
            traded = quantity if action == "BUY" else -min(quantity, before) if action == "SELL" else 0
            after = before + traded
            positions[symbol] = after

            market_return = round(.004 * math.sin(cycle * 1.17 + symbol_index * .83) - (.012 if cycle in {7, 10} else 0), 6)
            prices[symbol] = round(prices[symbol] * (1 + market_return), 4)
            pnl = round(after * prices[symbol] * market_return - abs(traded) * prices[symbol] * .0006, 2)
            expected_pnl = round(after * prices[symbol] * .0012, 2)
            equities[symbol] = round(equities[symbol] + pnl, 2)
            inputs = strategy_inputs(symbol, cycle)
            reason = decision_reason(symbol, action, inputs)
            cycle_start = start + timedelta(minutes=45 * cycle + 7 * symbol_index)
            ids = {kind: f"{symbol.lower()}-{kind}-{cycle:02d}" for kind in LIFECYCLE}

            common = {
                "symbol": symbol, "price": prices[symbol], "return": market_return,
                "pnl": pnl, "equity": equities[symbol], "expected_pnl": expected_pnl,
                "implementation_shortfall": round(expected_pnl - pnl, 2),
                "volatility": round(.14 + symbol_index * .035 + abs(market_return) * 7, 4),
                "volume_ratio": round(1.0 + .18 * math.cos(cycle + symbol_index), 3),
                "spread_bps": round(1.2 + symbol_index * .35 + abs(market_return) * 80, 3),
                "slippage_bps": round(.5 + abs(traded) / 100 + abs(market_return) * 35, 3),
                "signal_strength": round(min(1, abs(float(strategy["primary"][cycle])) / (70 if symbol == "AAPL" else 8)), 3),
                "news_risk": round(.1 + .07 * ((cycle + symbol_index) % 5), 3),
                **inputs,
            }

            for offset, kind in enumerate(LIFECYCLE):
                timestamp = (cycle_start + timedelta(minutes=offset)).isoformat().replace("+00:00", "Z")
                observation_time = cycle_start.isoformat().replace("+00:00", "Z")
                decision_time = (cycle_start + timedelta(minutes=1)).isoformat().replace("+00:00", "Z")
                row = {field: "" for field in FIELDS}
                row.update(common)
                row.update({
                    "timestamp": timestamp, "action": action if kind == "decision" else "",
                    "decision_reason": reason if kind == "decision" else "",
                    "target_position": after if kind in {"decision", "target"} else "",
                    "target_quantity": after if kind == "target" else "",
                    "target_weight": round(after * prices[symbol] / 1_000_000, 6) if kind in {"decision", "target"} else "",
                    "fill_quantity": traded if kind == "fill" else "",
                    "fill_price": prices[symbol] if kind == "fill" and traded else "",
                    "position_quantity": after if kind == "position" else "",
                    "kind": kind, "event_id": ids[kind],
                    "parent_id": ids[LIFECYCLE[offset - 1]] if offset else "",
                    "available_at": observation_time if kind in {"observation", "decision"} else timestamp,
                    "decision_timestamp": decision_time if kind == "decision" else "",
                    "strategy_id": f"demo-{symbol.lower()}-{str(strategy['name']).lower().replace(' ', '-')}",
                    "strategy_version": "2026.08-demo",
                    "model_version": strategy["model"] if kind == "decision" else "",
                    "feature_snapshot_id": f"{symbol.lower()}-features-{cycle:02d}" if kind == "decision" else "",
                    "detail": f"{kind.title()} evidence for {symbol} cycle {cycle + 1}.",
                })
                rows.append(row)

    return sorted(rows, key=lambda row: str(row["timestamp"]))


if __name__ == "__main__":
    rows = build_rows()
    with OUTPUT.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows)} rows to {OUTPUT}")
