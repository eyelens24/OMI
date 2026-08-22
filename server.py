"""Local Quant Doctor prototype. Run with: python3 server.py"""
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from datetime import datetime, timedelta, timezone
import ast
import bisect
import csv
import hashlib
import io
import json
import math
import random
import re
from statistics import mean, median, pstdev
from urllib.parse import parse_qs, urlparse
from storage import InvestigationStore
from incident_bundle import BundleValidationError, validate_incident_bundle
from attribution import attribute_pnl
from investigation_graph import build_investigation_graph, reconstruct_as_of
from synthetic_ground_truth import scenario_catalog
from evidence_flow import build_evidence_flow
from investigation_snapshot import make_snapshot
from hardening import adapt_read_only_bundle, reconcile_lifecycle, bounded_counterfactuals, make_reproducibility_receipt, incident_command
from omi_core.ledger import ledger_for_records
from omi_core.ai_forensics import assess_ai_decision
from omi_core.imports import validate_event_bundle
from omi_core.profiling import detected_decision, inspect_strategy

ROOT = Path(__file__).parent
STORE = InvestigationStore(ROOT / "data" / "quant_doctor.db")

FLIGHT_EVENT_TYPES = {
    "fundamental_snapshot", "strategy_decision", "portfolio_target", "order", "fill",
    "position_snapshot", "pnl_mark", "heartbeat", "data_status",
}


def corr(a, b):
    n = min(len(a), len(b))
    if n < 3:
        return 0.0
    a, b = a[:n], b[:n]
    am, bm = mean(a), mean(b)
    numerator = sum((x - am) * (y - bm) for x, y in zip(a, b))
    denominator = math.sqrt(sum((x - am) ** 2 for x in a) * sum((y - bm) ** 2 for y in b))
    return numerator / denominator if denominator else 0.0


def ranks(values):
    indexed = sorted(enumerate(values), key=lambda item: item[1])
    result = [0.0] * len(values)
    position = 0
    while position < len(indexed):
        end = position
        while end + 1 < len(indexed) and indexed[end + 1][1] == indexed[position][1]:
            end += 1
        rank = (position + end + 2) / 2
        for index in range(position, end + 1):
            result[indexed[index][0]] = rank
        position = end + 1
    return result


def spearman(a, b):
    return corr(ranks(a), ranks(b))


def partial_corr(x, y, control):
    rxy, rxz, ryz = corr(x, y), corr(x, control), corr(y, control)
    denominator = math.sqrt(max(0.000001, (1 - rxz ** 2) * (1 - ryz ** 2)))
    return (rxy - rxz * ryz) / denominator


def normal_cdf(value):
    return (1 + math.erf(value / math.sqrt(2))) / 2


def p_value_from_correlation(r, n):
    # Fisher transformation; a useful approximation for a prototype.
    if n < 5 or abs(r) >= 1:
        return 0.001
    z = abs(math.atanh(r)) * math.sqrt(n - 3)
    return max(0.0001, 2 * (1 - normal_cdf(z)))


def best_lag(source, target, maximum=36):
    candidates = []
    for lag in range(0, min(maximum, len(source) // 3)):
        score = corr(source[:-lag or None], target[lag:])
        candidates.append((abs(score), score, lag))
    _, score, lag = max(candidates)
    return score, lag


def z_score(values):
    baseline = values[: max(20, len(values) // 2)]
    deviation = pstdev(baseline) or 0.000001
    return (mean(values[-20:]) - mean(baseline)) / deviation


def detect_change(values, timestamps):
    minimum = max(20, len(values) // 10)
    best = (0.0, minimum)
    for point in range(minimum, len(values) - minimum):
        difference = abs(mean(values[point - minimum:point]) - mean(values[point:point + minimum]))
        if difference > best[0]:
            best = (difference, point)
    return {"timestamp": timestamps[best[1]], "magnitude": best[0]}


def synthetic_dataset(rows=720):
    random.seed(19)
    start = datetime(2025, 8, 14, 9, 30)
    records = []
    price, equity = 100.0, 0.0
    for index in range(rows):
        shock = 1 if index >= 430 else 0
        volatility = 0.12 + 0.025 * math.sin(index / 30) + shock * 0.15 + random.gauss(0, 0.012)
        volume = max(0.15, 1.0 + .12 * math.sin(index / 20) - shock * .34 + random.gauss(0, .06))
        spread = 1.8 + volatility * 7.4 + (1 - volume) * 2.5 + random.gauss(0, .18)
        slippage = max(.05, .34 * spread + .48 * (1 - volume) + random.gauss(0, .12))
        news_risk = max(0, random.gauss(.2, .08) + shock * .52 + (0.2 if index in range(450, 486) else 0))
        signal = .74 - shock * .39 - volatility * .35 + random.gauss(0, .05)
        market_return = random.gauss(0, volatility / 100)
        strategy_return = signal * .0014 - slippage / 10000 + random.gauss(0, .00022)
        expected_signal = .74 - volatility * .35
        expected_slippage = .34 * (1.8 + volatility * 7.4)
        expected_return = expected_signal * .0014 - expected_slippage / 10000
        equity += strategy_return * 1_000_000
        price *= 1 + market_return
        records.append({
            "timestamp": (start + timedelta(minutes=5 * index)).isoformat(), "price": round(price, 4),
            "return": market_return, "pnl": round(strategy_return * 1_000_000, 2), "equity": round(equity, 2),
            "expected_pnl": round(expected_return * 1_000_000, 2), "implementation_shortfall": round((expected_return - strategy_return) * 1_000_000, 2),
            "volatility": round(volatility, 5), "volume_ratio": round(volume, 4), "spread_bps": round(spread, 4),
            "slippage_bps": round(slippage, 4), "signal_strength": round(signal, 4), "news_risk": round(news_risk, 4),
        })
    return records


def synthetic_incident():
    records = synthetic_dataset()
    return records, {
        "root_cause": "Market stress regime",
        "onset": records[430]["timestamp"],
        "expected_mechanisms": ["Volatility shock", "Liquidity contraction", "Wider spreads", "Slippage", "Signal deterioration"],
    }


def load_sample(name):
    allowed = {"full-product": "full_product_demo.csv"}
    if name not in allowed:
        raise ValueError("Unknown sample dataset.")
    with (ROOT / "sample_data" / allowed[name]).open(newline="") as handle:
        return list(csv.DictReader(handle))


FIELD_ALIASES = {
    "time": "timestamp", "datetime": "timestamp", "date_time": "timestamp", "date": "timestamp",
    "realized_pnl": "pnl", "realised_pnl": "pnl", "net_pnl": "pnl", "profit_loss": "pnl", "pl": "pnl",
}


def canonical_field(name):
    normalised = re.sub(r"[^a-z0-9]+", "_", name.strip().lower()).strip("_")
    return FIELD_ALIASES.get(normalised, normalised)


def parse_csv_text(text, source_name):
    """Parse one uploaded CSV and normalise common timestamp/P&L headings."""
    if not isinstance(text, str) or not text.strip():
        raise ValueError(f"{source_name} CSV is empty.")
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise ValueError(f"{source_name} CSV needs a header row.")
    fields = [canonical_field(field) for field in reader.fieldnames]
    if len(set(fields)) != len(fields):
        raise ValueError(f"{source_name} CSV has duplicate columns after normalising headings.")
    rows = []
    for line_number, row in enumerate(reader, start=2):
        if not any(value and value.strip() for value in row.values()):
            continue
        normalised = {canonical_field(key): (value.strip() if isinstance(value, str) else value) for key, value in row.items()}
        if not normalised.get("timestamp"):
            raise ValueError(f"{source_name} CSV row {line_number} has no timestamp.")
        rows.append(normalised)
    if not rows:
        raise ValueError(f"{source_name} CSV has no data rows.")
    return rows


def parse_timestamp(value, source_name):
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        raise ValueError(f"{source_name} has an invalid ISO-8601 timestamp: {value!r}.")
    if parsed.tzinfo:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def normalise_flight_event(event):
    """Validate one read-only observer event before it is persisted."""
    if not isinstance(event, dict):
        raise ValueError("Each flight-recorder event must be an object.")
    strategy_id = str(event.get("strategy_id", "")).strip()
    event_type = str(event.get("event_type", "")).strip().lower()
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", strategy_id):
        raise ValueError("strategy_id must use letters, numbers, dots, hyphens, or underscores.")
    if event_type not in FLIGHT_EVENT_TYPES:
        raise ValueError(f"Unsupported event_type. Use one of: {', '.join(sorted(FLIGHT_EVENT_TYPES))}.")
    timestamp = parse_timestamp(event.get("timestamp"), "Flight-recorder event").isoformat()
    symbol = str(event.get("symbol", "")).strip().upper() or None
    data = event.get("data", {})
    if not isinstance(data, dict):
        raise ValueError("Flight-recorder event data must be an object.")
    normalised_data = {canonical_field(str(key)): value for key, value in data.items() if canonical_field(str(key)) not in {"timestamp", "symbol"}}
    for field in ("available_at", "decision_timestamp"):
        if normalised_data.get(field):
            normalised_data[field] = parse_timestamp(normalised_data[field], f"Flight-recorder {field}").isoformat()
    event_id = str(event.get("event_id", "")).strip()
    if not event_id:
        fingerprint = json.dumps({"strategy_id": strategy_id, "event_type": event_type, "timestamp": timestamp, "symbol": symbol, "data": normalised_data}, sort_keys=True, default=str)
        event_id = hashlib.sha256(fingerprint.encode()).hexdigest()
    return {"event_id": event_id, "strategy_id": strategy_id, "event_type": event_type, "timestamp": timestamp, "symbol": symbol, "data": normalised_data}


def flight_events_to_records(events):
    """As-of join recorded evidence to each P&L mark without using future data."""
    latest_by_symbol, records = {}, []
    for event in events:
        symbol = event.get("symbol") or "__aggregate"
        snapshot = latest_by_symbol.setdefault(symbol, {})
        if event["event_type"] == "pnl_mark":
            # Copy the state first: the P&L mark is an outcome, and must not
            # accidentally become input data for the next event.
            row = {"timestamp": event["timestamp"], **snapshot, **event["data"]}
            if symbol != "__aggregate":
                row["symbol"] = symbol
            if first_number(row, ("pnl", "realised_pnl", "realized_pnl", "net_pnl")) is not None:
                records.append(row)
        else:
            snapshot.update(event["data"])
    return records


FLIGHT_TO_LIFECYCLE = {
    "fundamental_snapshot": "observation",
    "strategy_decision": "decision",
    "portfolio_target": "target",
    "fill": "fill",
    "position_snapshot": "position",
    "pnl_mark": "pnl",
}


def flight_events_to_evidence(events):
    """Restore recorder events to the typed evidence format used by the UI."""
    evidence = []
    for event in events:
        data = dict(event.get("data") or {})
        kind = data.pop("kind", None) or FLIGHT_TO_LIFECYCLE.get(event.get("event_type"))
        if kind not in {"observation", "decision", "target", "fill", "position", "pnl"}:
            continue
        evidence.append({
            **data,
            "kind": kind,
            "event_id": event.get("event_id"),
            "timestamp": event.get("timestamp"),
            "symbol": event.get("symbol"),
        })
    return evidence


def typed_events_to_outcome_records(events):
    """Build one no-lookahead analysis row for every typed P&L event."""
    latest_by_symbol, records = {}, []
    metadata = {"kind", "event_id", "parent_id", "timestamp", "available_at", "raw_artifact_hash"}
    for event in sorted(events, key=lambda item: str(item.get("timestamp", ""))):
        symbol = event.get("symbol") or "__aggregate"
        snapshot = latest_by_symbol.setdefault(symbol, {})
        values = {key: value for key, value in event.items() if key not in metadata and value not in (None, "") and not isinstance(value, (dict, list))}
        if event.get("kind") == "pnl":
            row = {"timestamp": event.get("timestamp"), **snapshot, **values}
            if symbol != "__aggregate":
                row["symbol"] = symbol
            records.append(row)
        else:
            snapshot.update(values)
            if isinstance(event.get("feature_values"), dict):
                snapshot.update(event["feature_values"])
    return records


def demo_flight_events():
    """Emit the one canonical CSV through the live-recorder event contract."""
    event_types = {value: key for key, value in FLIGHT_TO_LIFECYCLE.items()}
    events = []
    for row in load_sample("full-product"):
        kind = row.get("kind")
        data = {key: value for key, value in row.items() if key not in {"timestamp", "symbol", "event_id", "strategy_id"} and value not in (None, "")}
        events.append({
            "event_id": row.get("event_id"),
            "strategy_id": "demo-independent-strategies",
            "event_type": event_types[kind],
            "timestamp": row["timestamp"],
            "symbol": row.get("symbol"),
            "data": data,
        })
    return [normalise_flight_event(event) for event in events]


def align_market_and_strategy(market_rows, strategy_rows, max_gap_minutes=5):
    """As-of join strategy outcomes with prior or equal market observations."""
    try:
        max_gap_minutes = float(max_gap_minutes)
    except (TypeError, ValueError):
        raise ValueError("Maximum alignment gap must be a number of minutes.")
    if not 0 <= max_gap_minutes <= 1440:
        raise ValueError("Maximum alignment gap must be between 0 and 1,440 minutes.")
    if "timestamp" not in market_rows[0]:
        raise ValueError("Market CSV needs a timestamp column.")
    if "timestamp" not in strategy_rows[0]:
        raise ValueError("Strategy CSV needs a timestamp column.")
    if "pnl" not in strategy_rows[0]:
        raise ValueError("Strategy CSV needs a numeric pnl column (aliases such as net_pnl and realised_pnl are accepted).")
    symbol_aligned = "symbol" in market_rows[0] and "symbol" in strategy_rows[0]
    market_indexes = {}
    for row in market_rows:
        symbol = str(row.get("symbol", "")).strip().upper() if symbol_aligned else "__all__"
        if symbol_aligned and not symbol:
            raise ValueError("Market CSV has a blank symbol while symbol-aware alignment is enabled.")
        market_indexes.setdefault(symbol, []).append((parse_timestamp(row["timestamp"], "Market CSV"), row))
    for symbol, market_index in market_indexes.items():
        market_index.sort(key=lambda item: item[0])
        times = [item[0] for item in market_index]
        if len(set(times)) != len(times):
            scope = f" for {symbol}" if symbol_aligned else ""
            raise ValueError(f"Market CSV has duplicate timestamps{scope}. Aggregate it to one row per timestamp first.")
        market_indexes[symbol] = (times, market_index)
    merged, unmatched, gaps = [], 0, []
    for strategy_row in strategy_rows:
        strategy_time = parse_timestamp(strategy_row["timestamp"], "Strategy CSV")
        symbol = str(strategy_row.get("symbol", "")).strip().upper() if symbol_aligned else "__all__"
        if symbol not in market_indexes:
            unmatched += 1
            continue
        market_times, market_index = market_indexes[symbol]
        index = bisect.bisect_right(market_times, strategy_time) - 1
        if index < 0:
            unmatched += 1
            continue
        market_time, market_row = market_index[index]
        gap = (strategy_time - market_time).total_seconds() / 60
        if gap > max_gap_minutes:
            unmatched += 1
            continue
        # Strategy outputs win on name conflicts (especially pnl/equity). This
        # keeps the P&L being explained separate from market features.
        joined = dict(market_row)
        joined.update(strategy_row)
        joined["timestamp"] = strategy_row["timestamp"]
        merged.append(joined)
        gaps.append(gap)
    if len(merged) < 50:
        raise ValueError(f"Only {len(merged)} strategy rows matched market rows within {max_gap_minutes:g} minutes; at least 50 aligned rows are required.")
    return merged, {
        "market_rows": len(market_rows), "strategy_rows": len(strategy_rows), "matched_rows": len(merged),
        "unmatched_strategy_rows": unmatched, "max_gap_minutes": max_gap_minutes,
        "mean_gap_minutes": round(mean(gaps), 3) if gaps else None, "symbol_aligned": symbol_aligned,
    }


def first_number(row, fields):
    for field in fields:
        try:
            value = row.get(field)
            if value not in (None, ""):
                return float(value)
        except (TypeError, ValueError):
            continue
    return None


def basket_summary(records):
    """Summarise instrument activity without mistaking trades for holdings."""
    symbol_rows = [row for row in records if str(row.get("symbol", "")).strip()]
    if not symbol_rows:
        return {
            "available": False,
            "summary": "No symbol column was supplied, so this upload can only be analysed as an aggregate strategy.",
        }
    by_symbol, latest_positions, buys, sells = {}, {}, 0, 0
    for row in symbol_rows:
        symbol = str(row["symbol"]).strip().upper()
        item = by_symbol.setdefault(symbol, {"symbol": symbol, "rows": 0, "pnl": 0.0, "notional": 0.0, "has_pnl": False, "buy_count": 0, "sell_count": 0})
        item["rows"] += 1
        pnl = first_number(row, ("pnl", "realised_pnl", "realized_pnl", "net_pnl"))
        if pnl is not None:
            item["pnl"] += pnl
            item["has_pnl"] = True
        notional = first_number(row, ("position_notional", "market_value", "notional"))
        if notional is None:
            quantity, price = first_number(row, ("position_quantity", "quantity", "shares")), first_number(row, ("price", "fill_price", "close"))
            notional = abs(quantity * price) if quantity is not None and price is not None else 0.0
        item["notional"] += abs(notional)
        position_quantity = first_number(row, ("position_quantity",))
        if position_quantity is not None:
            position_value = first_number(row, ("position_notional", "market_value"))
            if position_value is None:
                price = first_number(row, ("price", "close"))
                position_value = position_quantity * price if price is not None else None
            if position_value is not None:
                timestamp = parse_timestamp(row["timestamp"], "Position snapshot")
                previous = latest_positions.get(symbol)
                if previous is None or timestamp >= previous["timestamp"]:
                    latest_positions[symbol] = {"symbol": symbol, "notional": abs(position_value), "timestamp": timestamp}
        side = str(row.get("side", "")).strip().lower()
        if side in {"buy", "b", "long"}:
            buys += 1
            item["buy_count"] += 1
        elif side in {"sell", "s", "short"}:
            sells += 1
            item["sell_count"] += 1
    instruments = list(by_symbol.values())
    exposure_items = list(latest_positions.values()) if latest_positions else instruments
    total_notional = sum(item["notional"] for item in exposure_items)
    for item in exposure_items:
        item["share"] = round(item["notional"] / total_notional, 4) if total_notional else None
    top_exposures = [
        {**item, "timestamp": item["timestamp"].isoformat() if isinstance(item.get("timestamp"), datetime) else item.get("timestamp")}
        for item in sorted(exposure_items, key=lambda item: item["notional"], reverse=True)[:5]
    ]
    top_losses = sorted((item for item in instruments if item["has_pnl"]), key=lambda item: item["pnl"])[:5]
    concentration = top_exposures[0]["share"] if top_exposures and total_notional else None
    return {
        "available": True, "symbols": len(instruments), "rows": len(symbol_rows), "buy_count": buys, "sell_count": sells,
        "activity_notional": round(total_notional, 2), "largest_activity_share": concentration,
        "exposure_basis": "latest position snapshot" if latest_positions else "trading activity",
        "top_exposures": top_exposures, "top_losses": top_losses,
        "summary": "Basket concentration uses the latest supplied position snapshot." if latest_positions else "This is activity concentration across uploaded symbol rows, not a current holdings snapshot.",
    }


def edge(source_name, source, target_name, target, control, sample_interval_minutes):
    pearson = corr(source, target)
    lag_score, lag = best_lag(source, target)
    pvalue = p_value_from_correlation(pearson, len(source))
    return {
        "source": source_name, "target": target_name, "pearson": round(pearson, 3),
        "spearman": round(spearman(source, target), 3), "partial": round(partial_corr(source, target, control), 3),
        "best_lag": f"{lag * sample_interval_minutes} min", "lag_correlation": round(lag_score, 3),
        "p_value": "< 0.0001" if pvalue < .0001 else f"{pvalue:.4f}", "sample_size": len(source),
        "p_value_number": pvalue,
        "confidence": round(min(99, max(45, (1 - pvalue) * 83 + abs(pearson) * 16))),
    }


def apply_fdr_correction(candidates):
    """Benjamini-Hochberg false-discovery adjustment across tested edges."""
    ordered = sorted(enumerate(candidates), key=lambda item: item[1]["p_value_number"])
    total, running = len(ordered), 1.0
    for rank, (index, candidate) in reversed(list(enumerate(ordered, start=1))):
        adjusted = min(running, candidate["p_value_number"] * total / rank)
        candidates[index]["q_value"] = round(adjusted, 6)
        candidates[index]["fdr_significant"] = adjusted <= 0.05
        running = adjusted


def label_for(field):
    labels = {
        "pnl": "Strategy loss", "volume_ratio": "Relative volume", "liquidity_contraction": "Liquidity contraction", "spread_bps": "Wider spreads",
        "slippage_bps": "Slippage", "signal_strength": "Signal strength", "signal_deterioration": "Signal deterioration", "volatility": "Volatility shock",
        "news_risk": "News risk", "strategy_loss": "Strategy loss", "market_stress_regime": "Market stress regime",
        "fundamental_stress": "Fundamental thesis stress", "earnings_revision_deterioration": "Earnings estimate cuts",
        "growth_slowdown": "Growth slowdown", "earnings_surprise_deterioration": "Downside earnings surprise", "cash_flow_support_deterioration": "Cash-flow support weakened",
        "analyst_support_deterioration": "Analyst support weakened", "valuation_stretch": "Valuation stretch", "balance_sheet_risk": "Balance-sheet risk",
        "point_in_time_data_lag": "Point-in-time data became stale",
        "stock_decline": "Stock decline", "earnings_revision_pct": "Earnings revisions", "earnings_surprise_pct": "Earnings surprise",
        "revenue_growth_yoy": "Revenue growth", "eps_growth_yoy": "EPS growth", "free_cash_flow_yield": "Free-cash-flow yield",
        "valuation_percentile": "Valuation percentile", "pe_ratio": "P/E ratio", "ev_to_ebitda": "EV / EBITDA",
        "debt_to_ebitda": "Debt / EBITDA", "interest_coverage": "Interest coverage", "analyst_target_upside": "Analyst target upside",
        "alpha_signal_deterioration": "Fundamental alpha signal deterioration", "portfolio_translation_gap": "Portfolio translation gap",
        "alpha_score": "Alpha score", "information_coefficient": "Information coefficient", "rank_ic": "Rank IC",
        "weight_error_bps": "Weight error", "target_actual_weight_gap_bps": "Target-to-actual weight gap",
        "fundamental_age_days": "Fundamental-data age", "as_of_lag_days": "As-of data lag", "revision_lag_days": "Revision-data lag",
    }
    return labels.get(field, field.replace("_", " ").title())


def numeric_columns(records):
    columns = {}
    for key in records[0]:
        if key == "timestamp":
            continue
        try:
            values = [float(row[key]) for row in records]
            if pstdev(values) > 0:
                columns[key] = values
        except (KeyError, TypeError, ValueError):
            continue
    return columns


def standardise(values):
    deviation = pstdev(values) or 1.0
    average = mean(values)
    return [(value - average) / deviation for value in values]


def solve_linear_system(matrix, vector):
    size = len(vector)
    augmented = [list(row) + [vector[index]] for index, row in enumerate(matrix)]
    for column in range(size):
        pivot = max(range(column, size), key=lambda row: abs(augmented[row][column]))
        if abs(augmented[pivot][column]) < 0.000001:
            continue
        augmented[column], augmented[pivot] = augmented[pivot], augmented[column]
        scale = augmented[column][column]
        augmented[column] = [value / scale for value in augmented[column]]
        for row in range(size):
            if row == column:
                continue
            factor = augmented[row][column]
            augmented[row] = [value - factor * pivot_value for value, pivot_value in zip(augmented[row], augmented[column])]
    return [augmented[row][-1] for row in range(size)]


def driver_attribution(data, pnl):
    candidates = [field for field in (
        "earnings_revision_pct", "revenue_growth_yoy", "eps_growth_yoy", "earnings_surprise_pct",
        "valuation_percentile", "free_cash_flow_yield", "debt_to_ebitda", "interest_coverage",
        "alpha_score", "information_coefficient", "rank_ic", "weight_error_bps", "target_actual_weight_gap_bps",
        "volatility", "volume_ratio", "spread_bps", "slippage_bps", "signal_strength",
    ) if field in data]
    if not candidates:
        return []
    columns = [standardise(data[field]) for field in candidates]
    target = standardise([-value for value in pnl])
    width = len(candidates)
    xtx = [[sum(columns[row][index] * columns[column][index] for index in range(len(target))) + (0.01 if row == column else 0) for column in range(width)] for row in range(width)]
    xty = [sum(columns[row][index] * target[index] for index in range(len(target))) for row in range(width)]
    coefficients = solve_linear_system(xtx, xty)
    return sorted(({"topic": label_for(field), "standardised_coefficient": round(value, 3)} for field, value in zip(candidates, coefficients)), key=lambda item: abs(item["standardised_coefficient"]), reverse=True)


def infer_regime(data):
    """Infer a two-state market regime with small, explainable k-means."""
    feature_directions = {
        # Do not use execution outcomes to define the regime. Doing so would make
        # a later "regime → slippage" explanation circular.
        "volatility": 1, "volume_ratio": -1,
    }
    available = [(field, direction) for field, direction in feature_directions.items() if field in data]
    if len(available) < 2:
        return None
    scores = [0.0] * len(next(iter(data.values())))
    for field, direction in available:
        normalised = standardise(data[field])
        scores = [score + direction * value for score, value in zip(scores, normalised)]
    scores = [score / len(available) for score in scores]
    low, high = min(scores), max(scores)
    assignments = [0] * len(scores)
    for _ in range(20):
        assignments = [0 if abs(value - low) <= abs(value - high) else 1 for value in scores]
        groups = [[value for value, assignment in zip(scores, assignments) if assignment == cluster] for cluster in (0, 1)]
        if not all(groups):
            return None
        new_low, new_high = mean(groups[0]), mean(groups[1])
        if abs(new_low - low) + abs(new_high - high) < 0.00001:
            break
        low, high = new_low, new_high
    stressed_cluster = 0 if low > high else 1
    regime = [1.0 if assignment == stressed_cluster else 0.0 for assignment in assignments]
    separation = abs(high - low) / (pstdev(scores) or 1.0)
    return {
        "series": regime, "features": [field for field, _ in available],
        "confidence": round(min(95, max(50, 50 + separation * 20))),
        "stress_share": round(sum(regime) / len(regime), 3),
    }


# Inputs are directionally normalised so a high score always means a weaker
# fundamental thesis. Two or more supplied fields are required; with only one
# fundamental column the app reports that column, but does not invent a regime.
FUNDAMENTAL_FIELD_SPECS = (
    ("earnings_revision_pct", -1), ("earnings_surprise_pct", -1),
    ("revenue_growth_yoy", -1), ("eps_growth_yoy", -1),
    ("free_cash_flow_yield", -1), ("analyst_target_upside", -1),
    ("valuation_percentile", 1), ("pe_ratio", 1), ("ev_to_ebitda", 1),
    ("debt_to_ebitda", 1), ("interest_coverage", -1),
)


def infer_fundamental_regime(data):
    available = [(field, direction) for field, direction in FUNDAMENTAL_FIELD_SPECS if field in data]
    if len(available) < 2:
        return None
    scores = [0.0] * len(next(iter(data.values())))
    for field, direction in available:
        scores = [score + direction * value for score, value in zip(scores, standardise(data[field]))]
    scores = [score / len(available) for score in scores]
    # Use the same explainable two-cluster method as the market regime, but the
    # features here are all fundamental inputs rather than price/execution data.
    low, high = min(scores), max(scores)
    assignments = [0] * len(scores)
    for _ in range(20):
        assignments = [0 if abs(value - low) <= abs(value - high) else 1 for value in scores]
        groups = [[value for value, assignment in zip(scores, assignments) if assignment == cluster] for cluster in (0, 1)]
        if not all(groups):
            return None
        new_low, new_high = mean(groups[0]), mean(groups[1])
        if abs(new_low - low) + abs(new_high - high) < 0.00001:
            break
        low, high = new_low, new_high
    stressed_cluster = 0 if low > high else 1
    regime = [1.0 if assignment == stressed_cluster else 0.0 for assignment in assignments]
    separation = abs(high - low) / (pstdev(scores) or 1.0)
    return {
        "series": regime, "features": [field for field, _ in available],
        "confidence": round(min(95, max(50, 50 + separation * 20))),
        "stress_share": round(sum(regime) / len(regime), 3),
    }


def infer_data_lineage_regime(data):
    """Cluster stale/delayed inputs separately from the fundamental thesis."""
    fields = ("fundamental_age_days", "as_of_lag_days", "revision_lag_days")
    available = [field for field in fields if field in data]
    if len(available) < 2:
        return None
    scores = [0.0] * len(next(iter(data.values())))
    for field in available:
        scores = [score + value for score, value in zip(scores, standardise(data[field]))]
    scores = [score / len(available) for score in scores]
    low, high = min(scores), max(scores)
    assignments = [0] * len(scores)
    for _ in range(20):
        assignments = [0 if abs(value - low) <= abs(value - high) else 1 for value in scores]
        groups = [[value for value, assignment in zip(scores, assignments) if assignment == cluster] for cluster in (0, 1)]
        if not all(groups):
            return None
        new_low, new_high = mean(groups[0]), mean(groups[1])
        if abs(new_low - low) + abs(new_high - high) < 0.00001:
            break
        low, high = new_low, new_high
    stressed_cluster = 0 if low > high else 1
    regime = [1.0 if assignment == stressed_cluster else 0.0 for assignment in assignments]
    separation = abs(high - low) / (pstdev(scores) or 1.0)
    return {
        "series": regime, "features": available,
        "confidence": round(min(95, max(50, 50 + separation * 20))),
        "stress_share": round(sum(regime) / len(regime), 3),
    }


def causal_level(field):
    levels = {
        "market_stress_regime": 0, "fundamental_stress": 0, "news_risk": 0,
        "volatility": 1, "liquidity_contraction": 1,
        "earnings_revision_deterioration": 1, "growth_slowdown": 1, "earnings_surprise_deterioration": 1, "cash_flow_support_deterioration": 1,
        "analyst_support_deterioration": 1, "valuation_stretch": 1, "balance_sheet_risk": 1, "point_in_time_data_lag": 1,
        "signal_deterioration": 2, "alpha_signal_deterioration": 2, "spread_bps": 2,
        "stock_decline": 3, "portfolio_translation_gap": 3,
        "slippage_bps": 3, "strategy_loss": 4,
    }
    return levels.get(field, 2)


def explain_edge(source_key, target_key, confidence):
    templates = {
        ("fundamental_stress", "earnings_revision_deterioration"): "The weaker fundamental period coincided with more negative earnings-estimate revisions.",
        ("fundamental_stress", "growth_slowdown"): "The weaker fundamental period coincided with slower reported growth.",
        ("fundamental_stress", "earnings_surprise_deterioration"): "The weaker fundamental period coincided with worse earnings surprises.",
        ("fundamental_stress", "cash_flow_support_deterioration"): "The weaker fundamental period coincided with lower free-cash-flow support.",
        ("fundamental_stress", "analyst_support_deterioration"): "The weaker fundamental period coincided with lower analyst-implied upside.",
        ("fundamental_stress", "valuation_stretch"): "The weaker fundamental period coincided with a more stretched valuation measure.",
        ("fundamental_stress", "balance_sheet_risk"): "The weaker fundamental period coincided with higher balance-sheet risk.",
        ("fundamental_stress", "alpha_signal_deterioration"): "The weaker fundamental period coincided with a weaker fundamental-alpha score.",
        ("earnings_revision_deterioration", "stock_decline"): "More negative earnings revisions coincided with weaker stock returns.",
        ("growth_slowdown", "stock_decline"): "Slower growth coincided with weaker stock returns.",
        ("earnings_surprise_deterioration", "stock_decline"): "Worse earnings surprises coincided with weaker stock returns.",
        ("cash_flow_support_deterioration", "stock_decline"): "Lower free-cash-flow support coincided with weaker stock returns.",
        ("analyst_support_deterioration", "stock_decline"): "Lower analyst-implied upside coincided with weaker stock returns.",
        ("valuation_stretch", "stock_decline"): "More stretched valuations coincided with weaker stock returns.",
        ("balance_sheet_risk", "stock_decline"): "Higher balance-sheet risk coincided with weaker stock returns.",
        ("alpha_signal_deterioration", "stock_decline"): "A weaker fundamental-alpha score coincided with weaker stock returns.",
        ("alpha_signal_deterioration", "portfolio_translation_gap"): "A weaker alpha signal coincided with a larger gap between intended and realised portfolio weights.",
        ("portfolio_translation_gap", "strategy_loss"): "A larger target-to-actual weight gap coincided with larger realised strategy losses.",
        ("point_in_time_data_lag", "alpha_signal_deterioration"): "Older point-in-time inputs coincided with a weaker alpha signal.",
        ("point_in_time_data_lag", "portfolio_translation_gap"): "Older point-in-time inputs coincided with a larger target-to-actual weight gap.",
        ("point_in_time_data_lag", "strategy_loss"): "Older point-in-time inputs coincided with larger realised strategy losses; test whether stale data entered the decision process.",
        ("stock_decline", "strategy_loss"): "The stock decline coincided with larger realised strategy losses.",
        ("market_stress_regime", "volatility"): "The stressed period contained unusually high volatility.",
        ("market_stress_regime", "liquidity_contraction"): "The stressed period contained lower relative trading volume.",
        ("volatility", "spread_bps"): "Higher volatility coincided with wider quoted spreads.",
        ("volatility", "signal_deterioration"): "Higher volatility coincided with a weaker strategy signal.",
        ("liquidity_contraction", "spread_bps"): "Lower relative volume coincided with wider quoted spreads.",
        ("liquidity_contraction", "slippage_bps"): "Lower relative volume coincided with higher slippage.",
        ("spread_bps", "slippage_bps"): "Wider quoted spreads coincided with higher slippage.",
        ("slippage_bps", "strategy_loss"): "Higher slippage coincided with larger realised losses.",
        ("signal_deterioration", "strategy_loss"): "A weaker signal coincided with larger realised losses.",
    }
    return templates.get((source_key, target_key), f"{label_for(source_key)} and {label_for(target_key)} move together with {confidence}% statistical confidence in this sample.")


# These are the only directed links shown in the main cause map. They reflect a
# domain model of how market conditions can reach P&L; a correlation alone is
# never allowed to invent a backwards arrow in the user-facing explanation.
CAUSE_MAP_LINKS = {
    ("fundamental_stress", "earnings_revision_deterioration"),
    ("fundamental_stress", "growth_slowdown"),
    ("fundamental_stress", "earnings_surprise_deterioration"),
    ("fundamental_stress", "cash_flow_support_deterioration"),
    ("fundamental_stress", "analyst_support_deterioration"),
    ("fundamental_stress", "valuation_stretch"),
    ("fundamental_stress", "balance_sheet_risk"),
    ("fundamental_stress", "alpha_signal_deterioration"),
    ("earnings_revision_deterioration", "stock_decline"),
    ("growth_slowdown", "stock_decline"),
    ("earnings_surprise_deterioration", "stock_decline"),
    ("cash_flow_support_deterioration", "stock_decline"),
    ("analyst_support_deterioration", "stock_decline"),
    ("valuation_stretch", "stock_decline"),
    ("balance_sheet_risk", "stock_decline"),
    ("alpha_signal_deterioration", "stock_decline"),
    ("alpha_signal_deterioration", "portfolio_translation_gap"),
    ("portfolio_translation_gap", "strategy_loss"),
    ("point_in_time_data_lag", "alpha_signal_deterioration"),
    ("point_in_time_data_lag", "portfolio_translation_gap"),
    ("point_in_time_data_lag", "strategy_loss"),
    ("stock_decline", "strategy_loss"),
    ("market_stress_regime", "volatility"),
    ("market_stress_regime", "liquidity_contraction"),
    ("volatility", "spread_bps"),
    ("volatility", "signal_deterioration"),
    ("liquidity_contraction", "spread_bps"),
    ("liquidity_contraction", "slippage_bps"),
    ("spread_bps", "slippage_bps"),
    ("slippage_bps", "strategy_loss"),
    ("signal_deterioration", "strategy_loss"),
}


def format_measure(field, value):
    if field == "strategy_loss":
        return f"${-value:,.0f} P&L"
    if field in {"spread_bps", "slippage_bps"}:
        return f"{value:.2f} bps"
    if field == "volume_ratio":
        return f"{value:.2f}× normal volume"
    if field == "liquidity_contraction":
        return f"{-value:.2f}× normal volume"
    if field == "signal_strength":
        return f"{value:.2f} signal strength"
    if field == "signal_deterioration":
        return f"{-value:.2f} signal strength"
    if field == "news_risk":
        return f"{value:.2f} news-risk score"
    if field == "volatility":
        return f"{value:.3f} realised volatility"
    if field in {"earnings_revision_pct", "earnings_surprise_pct", "revenue_growth_yoy", "eps_growth_yoy", "free_cash_flow_yield", "analyst_target_upside"}:
        return f"{value:.2f}%"
    if field == "valuation_percentile":
        return f"{value:.0%} valuation percentile"
    if field in {"pe_ratio", "ev_to_ebitda", "debt_to_ebitda", "interest_coverage"}:
        return f"{value:.2f}×"
    if field == "stock_decline":
        return f"{-value:.2%} return"
    if field in {"weight_error_bps", "target_actual_weight_gap_bps"}:
        return f"{value:.1f} bps"
    if field in {"fundamental_age_days", "as_of_lag_days", "revision_lag_days"}:
        return f"{value:.1f} days"
    return f"{value:.3f}"


def evidence_detail(source_key, target_key, source, target):
    """A concrete high-stress-versus-other comparison for a displayed arrow."""
    if source_key in {"market_stress_regime", "fundamental_stress"}:
        focused = [value for source_value, value in zip(source, target) if source_value >= 0.5]
        other = [value for source_value, value in zip(source, target) if source_value < 0.5]
        condition = "During the inferred fundamental-stress period" if source_key == "fundamental_stress" else "During the inferred stressed period"
    else:
        threshold = median(source)
        focused = [value for source_value, value in zip(source, target) if source_value >= threshold]
        other = [value for source_value, value in zip(source, target) if source_value < threshold]
        condition = f"When {label_for(source_key).lower()} was higher"
    if not focused or not other:
        return "The available observations did not support a stable high-versus-low comparison."
    if target_key == "strategy_loss":
        return f"{condition}, realised P&L averaged {format_measure(target_key, mean(focused))}, versus {format_measure(target_key, mean(other))} in the comparison observations."
    return f"{condition}, {label_for(target_key).lower()} averaged {format_measure(target_key, mean(focused))}, versus {format_measure(target_key, mean(other))} in the comparison observations."


FUNDAMENTAL_DOMAIN_SPECS = (
    ("earnings", "Earnings and growth", "Reported growth, earnings surprises, and cash-generation evidence.", (
        ("revenue_growth_yoy", "Revenue growth", -1), ("eps_growth_yoy", "EPS growth", -1),
        ("earnings_surprise_pct", "Earnings surprise", -1), ("free_cash_flow_yield", "Free-cash-flow yield", -1),
    )),
    ("estimates", "Forward estimates", "Sell-side estimate revisions and the remaining target-price upside.", (
        ("earnings_revision_pct", "Earnings revisions", -1), ("analyst_target_upside", "Analyst target upside", -1),
    )),
    ("valuation", "Valuation", "Relative valuation measures. Whether a high valuation is bad depends on the strategy thesis.", (
        ("valuation_percentile", "Valuation percentile", 1), ("pe_ratio", "P/E ratio", 1),
        ("ev_to_ebitda", "EV / EBITDA", 1), ("free_cash_flow_yield", "Free-cash-flow yield", -1),
    )),
    ("balance_sheet", "Balance sheet", "Leverage and debt-service capacity.", (
        ("debt_to_ebitda", "Debt / EBITDA", 1), ("interest_coverage", "Interest coverage", -1),
    )),
)


ALPHA_DEBUGGER_DOMAIN_SPECS = (
    ("signal_validity", "Fundamental signal validity", "Did the strategy's own fundamental alpha signal still predict returns?", (
        ("alpha_score", "Alpha score", -1), ("expected_return", "Expected return", -1),
        ("information_coefficient", "Information coefficient", -1), ("rank_ic", "Rank IC", -1),
        ("hit_rate", "Hit rate", -1),
    )),
    ("portfolio_translation", "Portfolio translation", "Did ranking and target weights translate faithfully into the realised portfolio?", (
        ("weight_error_bps", "Weight error", 1), ("target_actual_weight_gap_bps", "Target-to-actual weight gap", 1),
        ("factor_exposure_error", "Factor exposure error", 1),
    )),
    ("point_in_time", "Point-in-time data lineage", "Could the strategy have used stale, delayed, or revised-after-the-fact fundamentals?", (
        ("fundamental_age_days", "Fundamental-data age", 1), ("as_of_lag_days", "As-of data lag", 1),
        ("revision_lag_days", "Revision-data lag", 1), ("restatement_gap_pct", "Restatement gap", 1),
    )),
)


# These are candidate upstream causes, not generic metrics. They are ranked by
# adverse shift, timing, and association with the strategy loss. The user sees
# the raw business/research issue (for example estimate cuts), rather than the
# derived aggregate regime that merely groups several observations together.
ROOT_CAUSE_CANDIDATE_SPECS = (
    ("earnings_revision_pct", "Earnings expectations were cut", -1, "Forward earnings estimates moved down, weakening the thesis used by the strategy."),
    ("revenue_growth_yoy", "Revenue growth slowed", -1, "Growth data weakened relative to the earlier period."),
    ("eps_growth_yoy", "EPS growth slowed", -1, "Earnings growth weakened relative to the earlier period."),
    ("earnings_surprise_pct", "Earnings surprised to the downside", -1, "Reported earnings outcomes deteriorated versus expectations."),
    ("free_cash_flow_yield", "Cash-flow support weakened", -1, "Free-cash-flow yield fell relative to the earlier period."),
    ("debt_to_ebitda", "Balance-sheet leverage increased", 1, "Debt relative to EBITDA increased."),
    ("interest_coverage", "Debt-service capacity weakened", -1, "Interest coverage deteriorated."),
    ("alpha_score", "The fundamental alpha signal decayed", -1, "The strategy's own alpha score fell."),
    ("information_coefficient", "The alpha signal lost predictive power", -1, "The relationship between the signal and subsequent return weakened."),
    ("rank_ic", "The alpha ranking lost predictive power", -1, "The rank ordering of expected returns weakened."),
    ("weight_error_bps", "Target weights diverged from realised weights", 1, "The intended portfolio was not translated cleanly into realised positions."),
    ("target_actual_weight_gap_bps", "Portfolio translation gap widened", 1, "The gap between target and actual portfolio weights increased."),
    ("fundamental_age_days", "Fundamental data became stale", 1, "The strategy was working with older fundamental inputs."),
    ("as_of_lag_days", "Point-in-time data lag increased", 1, "The available data lagged the decision timestamp by more than before."),
    ("revision_lag_days", "Estimate-revision data arrived late", 1, "The strategy received estimate revisions later than before."),
)


IMPLEMENTATION_DOMAIN_SPECS = (
    ("model", "Strategy / model", "Model drift, weakening predictions, or changed expected performance.", (
        ("signal_strength", "Signal strength", -1), ("expected_pnl", "Expected P&L", -1),
        ("hit_rate", "Hit rate", -1), ("feature_drift_score", "Feature-drift score", 1),
        ("prediction_error", "Prediction error", 1),
    )),
    ("risk", "Risk / portfolio", "Sizing, leverage, concentration, and portfolio-risk changes.", (
        ("gross_exposure", "Gross exposure", 1), ("net_exposure", "Net exposure", 1),
        ("leverage", "Leverage", 1), ("concentration", "Concentration", 1),
        ("position_size", "Position size", 1), ("var_95", "Value at Risk", 1),
        ("expected_shortfall", "Expected shortfall", 1),
    )),
    ("execution", "Execution", "Costs, fills, rejects, latency, and broker reconciliation.", (
        ("slippage_bps", "Slippage", 1), ("spread_bps", "Quoted spread", 1),
        ("fill_rate", "Fill rate", -1), ("reject_rate", "Reject rate", 1),
        ("latency_ms", "Order latency", 1), ("fees", "Fees", 1),
        ("broker_position_mismatch", "Broker position mismatch", 1),
    )),
    ("data", "Data quality", "Freshness, completeness, timestamps, and vendor reconciliation.", (
        ("data_age_ms", "Data age", 1), ("missing_rate", "Missing-data rate", 1),
        ("stale_ticks", "Stale ticks", 1), ("vendor_diff_bps", "Vendor-price difference", 1),
        ("clock_skew_ms", "Clock skew", 1),
    )),
    ("operations", "Operations", "API failures, restarts, deployments, and configuration changes.", (
        ("api_error_rate", "API error rate", 1), ("api_disconnects", "API disconnects", 1),
        ("restart_count", "Restart count", 1), ("order_reject_rate", "Order reject rate", 1),
    )),
)


def recent_change_finding(field, label, bad_direction, values):
    # A short initial baseline avoids averaging a sustained failure into the
    # reference period, which would hide a fault that began mid-investigation.
    baseline = values[: max(20, len(values) // 4)]
    recent = values[-max(20, len(values) // 10):]
    baseline_mean, recent_mean = mean(baseline), mean(recent)
    deviation = pstdev(baseline) or 0.000001
    score = (recent_mean - baseline_mean) / deviation
    severity_score = score * bad_direction
    displayed_score = max(-99.0, min(99.0, score))
    status = "alert" if severity_score >= 2 else "watch" if severity_score >= 1 else "healthy"
    direction = "higher" if bad_direction > 0 else "lower"
    return {
        "field": field, "label": label, "status": status, "z_score": round(displayed_score, 2),
        "baseline": round(baseline_mean, 5), "recent": round(recent_mean, 5),
        "detail": f"Recent average {recent_mean:.4g} versus baseline {baseline_mean:.4g} (z {displayed_score:+.2f}); {direction} values are treated as adverse for this check.",
    }


def adverse_change_point(values, bad_direction, timestamps):
    """Find the earliest largest adverse break using two adjacent local windows."""
    window = max(20, len(values) // 10)
    best = (0.0, window)
    for point in range(window, len(values) - window + 1):
        before, after = mean(values[point - window:point]), mean(values[point:point + window])
        adverse_shift = (after - before) * bad_direction
        if adverse_shift > best[0]:
            best = (adverse_shift, point)
    return {"timestamp": timestamps[best[1]], "magnitude": best[0]}


def root_cause_candidates(data, timestamps, pnl):
    """Rank testable upstream explanations without turning association into proof."""
    candidates = []
    loss = [-value for value in pnl]
    for field, title, bad_direction, mechanism in ROOT_CAUSE_CANDIDATE_SPECS:
        if field not in data:
            continue
        finding = recent_change_finding(field, label_for(field), bad_direction, data[field])
        if finding["status"] == "healthy":
            continue
        onset = adverse_change_point(data[field], bad_direction, timestamps)
        association = corr([bad_direction * value for value in data[field]], loss)
        severity = max(0.0, finding["z_score"] * bad_direction)
        # Earlier changes get a modest advantage over equally severe later
        # changes; the score is only for ordering the investigation queue.
        timing = 1 - (timestamps.index(onset["timestamp"]) / max(1, len(timestamps) - 1))
        score = severity * 0.65 + abs(association) * 2 + timing * 0.35
        candidates.append({
            "field": field, "title": title, "status": finding["status"], "score": round(score, 3),
            "onset": onset["timestamp"], "association": round(association, 3), "mechanism": mechanism,
            "detail": f"{mechanism} The largest adverse shift began around {onset['timestamp'].replace('T', ' ')[:16]}. {finding['detail']} Association with strategy loss: r = {association:+.2f}.",
        })
    return sorted(candidates, key=lambda item: item["score"], reverse=True)[:3]


def pattern_discovery(data, fundamental_regime, market_regime, lineage_regime):
    """Expose ML pattern detection without promoting clusters to causes.

    K-means answers whether selected observations form distinct groups; domain
    theory determines which features are safe to call stress. Any materially
    shifting numeric input outside the reviewed vocabulary is reported as an
    unclassified pattern for a reviewer, not auto-named as a root cause.
    """
    detectors = []
    for title, regime in (("Fundamental-state clustering", fundamental_regime), ("Market-state clustering", market_regime), ("Data-lineage clustering", lineage_regime)):
        if not regime:
            continue
        latest_state = "stressed cluster" if regime["series"][-1] >= .5 else "normal cluster"
        detectors.append({
            "title": title, "algorithm": "two-cluster k-means", "state": latest_state,
            "features": regime["features"], "confidence": regime["confidence"],
            "detail": f"The latest observation belongs to the {latest_state}. This detects a pattern in the supplied fields; it does not identify an external cause.",
        })
    reviewed = {
        "pnl", "return", "equity", "expected_pnl", "implementation_shortfall", "gross_signal_pnl", "price",
        "earnings_revision_pct", "earnings_surprise_pct", "revenue_growth_yoy", "eps_growth_yoy", "free_cash_flow_yield",
        "analyst_target_upside", "valuation_percentile", "pe_ratio", "ev_to_ebitda", "debt_to_ebitda", "interest_coverage",
        "alpha_score", "expected_return", "information_coefficient", "rank_ic", "weight_error_bps", "target_actual_weight_gap_bps",
        "fundamental_age_days", "as_of_lag_days", "revision_lag_days", "volatility", "volume_ratio", "spread_bps",
        "slippage_bps", "signal_strength", "news_risk",
    }
    unclassified = []
    for field, values in data.items():
        if field in reviewed:
            continue
        finding = recent_change_finding(field, label_for(field), 1, values)
        if finding["status"] in {"alert", "watch"}:
            unclassified.append({
                "field": field, "label": label_for(field), "status": finding["status"], "detail": finding["detail"],
            })
    return {"detectors": detectors, "unclassified_patterns": unclassified[:5]}


# A measured field is not itself a causal mechanism. This mapping gives each
# supported field a plain-English interpretation before the app follows only
# the statistically retained downstream links. Fields without an established
# downstream route remain useful candidates, but the UI must say that the
# route to P&L is not yet evidenced rather than inventing one.
ROOT_MECHANISM_BLOCKS = {
    "earnings_revision_pct": ("earnings_revision_deterioration", "Earnings expectations weakened", "Lower forward estimates weaken the earnings assumption behind the position."),
    "revenue_growth_yoy": ("growth_slowdown", "The growth assumption weakened", "Slower revenue growth weakens the growth assumption behind the position."),
    "eps_growth_yoy": ("growth_slowdown", "The growth assumption weakened", "Slower EPS growth weakens the growth assumption behind the position."),
    "earnings_surprise_pct": ("earnings_surprise_deterioration", "Reported results weakened", "Downside earnings surprises challenge the earnings assumption behind the position."),
    "free_cash_flow_yield": ("cash_flow_support_deterioration", "Cash-flow support weakened", "Lower free-cash-flow yield weakens the cash-generation assumption behind the position."),
    "analyst_target_upside": ("analyst_support_deterioration", "Analyst support weakened", "Lower analyst-implied upside weakens one external expectation input to the position."),
    "debt_to_ebitda": ("balance_sheet_risk", "Balance-sheet risk increased", "More debt relative to EBITDA makes the original financial-risk assumption less robust."),
    "interest_coverage": ("balance_sheet_risk", "Debt-service capacity weakened", "Lower interest coverage makes the original financial-risk assumption less robust."),
    "alpha_score": ("alpha_signal_deterioration", "The alpha signal weakened", "The strategy's own fundamental score became less favourable."),
    "information_coefficient": ("alpha_signal_deterioration", "The alpha signal weakened", "The score's relationship with subsequent returns weakened."),
    "rank_ic": ("alpha_signal_deterioration", "The alpha ranking weakened", "The rank ordering of expected returns became less reliable."),
    "weight_error_bps": ("portfolio_translation_gap", "The portfolio did not match its target", "The intended portfolio and realised portfolio diverged."),
    "target_actual_weight_gap_bps": ("portfolio_translation_gap", "The portfolio did not match its target", "The intended portfolio and realised portfolio diverged."),
    "fundamental_age_days": ("point_in_time_data_lag", "The decision inputs became stale", "The strategy was working with older fundamental inputs."),
    "as_of_lag_days": ("point_in_time_data_lag", "The decision inputs became stale", "The available inputs lagged the decision timestamp by more than before."),
    "revision_lag_days": ("point_in_time_data_lag", "The decision inputs became stale", "Estimate revisions reached the strategy later than before."),
}


def best_explanation_path(start_key, cause_map):
    """Return the strongest permitted route from one mechanism to strategy loss."""
    by_source = {}
    for item in cause_map:
        by_source.setdefault(item["source_key"], []).append(item)

    def walk(topic, seen=frozenset()):
        if topic == "strategy_loss":
            return []
        choices = [edge for edge in by_source.get(topic, []) if edge["target_key"] not in seen]
        paths = []
        for edge in choices:
            rest = walk(edge["target_key"], seen | {topic})
            if rest is not None:
                paths.append([edge, *rest])
        if not paths:
            return None
        return max(paths, key=lambda path: sum(edge.get("score", edge["confidence"]) for edge in path))

    return walk(start_key) or []


def dynamic_explanation_blocks(root_causes, cause_map, root_key):
    """Build a variable-length, evidence-led explanation for the UI.

    The first block comes from the actual leading candidate, not a derived
    regime label. Later blocks exist only where an allowed link was retained
    by the data. This keeps the explanation compact without pretending that
    every investigation has the same number of stages.
    """
    if root_causes:
        primary = root_causes[0]
        blocks = [{
            "id": f"observed:{primary['field']}", "kind": "observed", "stage": "FIRST MEASURED BREAK",
            "title": primary["title"], "copy": primary["mechanism"],
            "detail": f"Detected around {primary['onset'].replace('T', ' ')[:16]}. Association with strategy loss: r = {primary['association']:+.2f}.",
            "link": {"kind": "interpretation", "label": "MEANS", "detail": "This block translates the measured field into the investment or strategy assumption it challenges."},
        }]
        mechanism = ROOT_MECHANISM_BLOCKS.get(primary["field"])
        if not mechanism:
            blocks.append({
                "id": "untraced", "kind": "gap", "stage": "WHAT WE CANNOT YET TRACE",
                "title": "No supported route to P&L yet", "copy": "The change is a valid investigation lead, but the supplied data does not support a defined intermediate path from it to the loss.",
                "detail": "Add aligned returns, alpha decisions, target weights, or other relevant evidence before treating it as an explanation.",
                "link": {"kind": "interpretation", "label": "NOT EVIDENCED", "detail": "No measured downstream relationship was retained for this candidate."},
            })
            return blocks
        mechanism_key, mechanism_title, mechanism_copy = mechanism
        blocks.append({
            "id": mechanism_key, "kind": "mechanism", "stage": "WHAT THIS MAY WEAKEN",
            "title": mechanism_title, "copy": mechanism_copy,
            "detail": "This is the interpretation of the first measured break, not proof of an external event.",
        })
        route = best_explanation_path(mechanism_key, cause_map)
        for edge in route:
            blocks.append({
                "id": edge["target_key"], "kind": "outcome" if edge["target_key"] == "strategy_loss" else "effect",
                "stage": "OUTCOME" if edge["target_key"] == "strategy_loss" else "WHAT THE DATA SHOWED NEXT",
                "title": label_for(edge["target_key"]), "copy": edge["explanation"],
                "detail": f"{edge['confidence']}% statistical support in this sample.", "link": {"kind": "evidence", "edge": edge},
            })
        if not route:
            blocks.append({
                "id": "untraced", "kind": "gap", "stage": "WHAT WE CANNOT YET TRACE",
                "title": "No supported route to P&L yet", "copy": "The first break is clear, but this data set did not retain a supported downstream link to the strategy loss.",
                "detail": "That limits this result to a lead to investigate, not a complete explanation.",
                "link": {"kind": "interpretation", "label": "NOT EVIDENCED", "detail": "No measured downstream relationship was retained for this candidate."},
            })
        return blocks

    if root_key:
        return [{
            "id": "no_new_break", "kind": "gap", "stage": "WHAT THIS WINDOW DOES NOT SHOW",
            "title": "No new measurable break", "copy": "The selected loss occurred during an adverse pattern, but this decision window did not identify a specific new upstream change to rank.",
            "detail": "The loss may reflect a persistent earlier issue or evidence not present in the recorded fields. It is not a basis for naming a new root cause.",
        }]
    return []


def data_integrity_findings(records):
    findings = []
    populated_cells = missing_cells = 0
    for row in records:
        for key, value in row.items():
            if key == "timestamp":
                continue
            populated_cells += 1
            if value is None or (isinstance(value, str) and not value.strip()):
                missing_cells += 1
    if populated_cells:
        rate = missing_cells / populated_cells
        findings.append({
            "field": "raw_missing_cells", "label": "Blank data cells",
            "status": "alert" if rate >= .05 else "watch" if rate > 0 else "healthy",
            "detail": f"{missing_cells} of {populated_cells} non-timestamp cells were blank ({rate:.2%}).",
        })
    timestamps, invalid = [], 0
    symbol_aware = all(str(row.get("symbol", "")).strip() for row in records)
    for row in records:
        try:
            timestamps.append((str(row.get("symbol", "")).strip().upper() if symbol_aware else "__all__", parse_timestamp(row.get("timestamp"), "Uploaded data")))
        except ValueError:
            invalid += 1
    if invalid:
        findings.append({"field": "timestamp_parse", "label": "Timestamp format", "status": "alert", "detail": f"{invalid} rows have invalid timestamps."})
    elif len(timestamps) >= 3:
        by_symbol = {}
        for symbol, timestamp in timestamps:
            by_symbol.setdefault(symbol, []).append(timestamp)
        duplicate_count, positive_intervals = 0, []
        for values in by_symbol.values():
            values.sort()
            intervals = [(later - earlier).total_seconds() for earlier, later in zip(values, values[1:])]
            duplicate_count += sum(interval == 0 for interval in intervals)
            positive_intervals.extend(interval for interval in intervals if interval > 0)
        typical = median(positive_intervals) if positive_intervals else 0
        long_gaps = sum(interval > typical * 2 for interval in positive_intervals) if typical else 0
        findings.append({
            "field": "timestamp_cadence", "label": "Symbol-timestamp continuity" if symbol_aware else "Timestamp continuity",
            "status": "alert" if duplicate_count else "watch" if long_gaps else "healthy",
            "detail": f"{duplicate_count} duplicate timestamps and {long_gaps} gaps greater than twice the typical {typical / 60:.1f}-minute interval.",
        })
    return findings


def operational_change_finding(records):
    for field in ("strategy_version", "model_version", "parameter_hash", "deployment_id"):
        values = [str(row[field]).strip() for row in records if row.get(field) not in (None, "")]
        if len(values) < 2:
            continue
        baseline, recent = values[: max(1, len(values) // 2)], values[-max(1, len(values) // 10):]
        baseline_mode = max(set(baseline), key=baseline.count)
        recent_mode = max(set(recent), key=recent.count)
        changed = baseline_mode != recent_mode
        return {
            "field": field, "label": field.replace("_", " ").title(),
            "status": "alert" if changed else "healthy",
            "detail": f"Baseline value: {baseline_mode}. Recent value: {recent_mode}." if changed else f"No recent change in {field.replace('_', ' ')}.",
        }
    return None


def audit_domains(records, data, specs, include_integrity=False, include_operations=False):
    """Assess only the thesis or system checks that the upload can evidence."""
    domains = []
    rank = {"healthy": 0, "watch": 1, "alert": 2}
    for domain_id, title, description, checks in specs:
        findings = [recent_change_finding(field, label, direction, data[field]) for field, label, direction in checks if field in data]
        missing = [field for field, _, _ in checks if field not in data]
        if include_integrity and domain_id == "data":
            findings.extend(data_integrity_findings(records))
        if include_operations and domain_id == "operations":
            change = operational_change_finding(records)
            if change:
                findings.append(change)
        if not findings:
            domains.append({
                "id": domain_id, "title": title, "status": "not_assessable", "description": description,
                "summary": f"Not assessable from this upload. Add one or more of: {', '.join(missing[:4])}.",
                "findings": [], "missing_fields": missing,
            })
            continue
        worst = max(findings, key=lambda finding: rank[finding["status"]])
        status = worst["status"]
        if status == "alert":
            summary = f"Potential fault detected: {worst['label']}. {worst['detail']}"
        elif status == "watch":
            summary = f"Change worth checking: {worst['label']}. {worst['detail']}"
        else:
            summary = f"No material recent fault was detected in the {len(findings)} available check{'s' if len(findings) != 1 else ''}."
        domains.append({
            "id": domain_id, "title": title, "status": status, "description": description,
            "summary": summary, "findings": findings, "missing_fields": missing,
        })
    return domains


def fundamental_fault_domains(records, data):
    return audit_domains(records, data, FUNDAMENTAL_DOMAIN_SPECS)


def alpha_debugger_domains(records, data):
    return audit_domains(records, data, ALPHA_DEBUGGER_DOMAIN_SPECS)


def implementation_fault_domains(records, data):
    return audit_domains(records, data, IMPLEMENTATION_DOMAIN_SPECS, include_integrity=True, include_operations=True)


def confirmation_plan(data, root_key):
    """Actions that can falsify the leading story; these are not trade advice."""
    steps = []
    if root_key == "fundamental_stress":
        steps.append("Run the strategy again with the exact point-in-time fundamental snapshots and estimate history available at each rebalance; do not use revised data.")
        steps.append("Compare the failing names with sector-, country-, and market-neutral controls to test whether the apparent thesis failure was actually a common exposure.")
    if any(field in data for field in ("alpha_score", "expected_return", "information_coefficient", "rank_ic")):
        steps.append("Measure signal validity before and during the incident: out-of-sample IC, rank IC, hit rate, and return by alpha-rank bucket.")
    if any(field in data for field in ("weight_error_bps", "target_actual_weight_gap_bps", "factor_exposure_error")):
        steps.append("Reprice the incident using target weights versus realised weights to isolate portfolio-construction and execution leakage from signal failure.")
    steps.append("Treat the result as a hypothesis until this replay and the relevant controls reject competing explanations.")
    return steps


def analyse(records):
    if len(records) < 50:
        raise ValueError("At least 50 timestamped observations are required for diagnosis.")
    data = numeric_columns(records)
    if "pnl" not in data:
        raise ValueError("Market data must contain a numeric pnl column. Other numeric columns are discovered automatically.")
    timestamps = [row["timestamp"] for row in records]
    pnl = data["pnl"]
    volatility = data.get("volatility", [0.0] * len(records))
    spread = data.get("spread_bps", [0.0] * len(records))
    slippage = data.get("slippage_bps", [0.0] * len(records))
    interval = 5
    series = dict(data)
    series["strategy_loss"] = [-value for value in pnl]
    if "return" in data:
        # The input return remains an outcome field, while this derived series
        # gives the map one unambiguous direction: higher = a worse stock move.
        series["stock_decline"] = [-value for value in data["return"]]
    # Directional, human-readable mechanism variables. The raw fields remain in
    # `data`, but the cause map uses increasing values to mean more stress.
    if "volume_ratio" in data:
        series["liquidity_contraction"] = [-value for value in data["volume_ratio"]]
    if "signal_strength" in data:
        series["signal_deterioration"] = [-value for value in data["signal_strength"]]
    # Fundamental mechanisms use one supplied representative measure each. The
    # full group of raw measures still feeds the upstream stress classifier and
    # the thesis-health cards; this avoids combining valuation multiples with
    # unrelated units inside a single displayed mechanism.
    if "earnings_revision_pct" in data:
        series["earnings_revision_deterioration"] = [-value for value in data["earnings_revision_pct"]]
    if "earnings_surprise_pct" in data:
        series["earnings_surprise_deterioration"] = [-value for value in data["earnings_surprise_pct"]]
    if "revenue_growth_yoy" in data:
        series["growth_slowdown"] = [-value for value in data["revenue_growth_yoy"]]
    elif "eps_growth_yoy" in data:
        series["growth_slowdown"] = [-value for value in data["eps_growth_yoy"]]
    if "valuation_percentile" in data:
        series["valuation_stretch"] = data["valuation_percentile"]
    elif "pe_ratio" in data:
        series["valuation_stretch"] = data["pe_ratio"]
    elif "ev_to_ebitda" in data:
        series["valuation_stretch"] = data["ev_to_ebitda"]
    if "debt_to_ebitda" in data:
        series["balance_sheet_risk"] = data["debt_to_ebitda"]
    elif "interest_coverage" in data:
        series["balance_sheet_risk"] = [-value for value in data["interest_coverage"]]
    if "free_cash_flow_yield" in data:
        series["cash_flow_support_deterioration"] = [-value for value in data["free_cash_flow_yield"]]
    if "analyst_target_upside" in data:
        series["analyst_support_deterioration"] = [-value for value in data["analyst_target_upside"]]
    if "alpha_score" in data:
        series["alpha_signal_deterioration"] = [-value for value in data["alpha_score"]]
    elif "expected_return" in data:
        series["alpha_signal_deterioration"] = [-value for value in data["expected_return"]]
    if "weight_error_bps" in data:
        series["portfolio_translation_gap"] = data["weight_error_bps"]
    elif "target_actual_weight_gap_bps" in data:
        series["portfolio_translation_gap"] = data["target_actual_weight_gap_bps"]
    lag_fields = [field for field in ("fundamental_age_days", "as_of_lag_days", "revision_lag_days") if field in data]
    if lag_fields:
        normalised_lags = [standardise(data[field]) for field in lag_fields]
        series["point_in_time_data_lag"] = [mean(values) for values in zip(*normalised_lags)]
    fundamental_regime = infer_fundamental_regime(data)
    market_regime = infer_regime(data)
    lineage_regime = infer_data_lineage_regime(data)
    # Fundamental mode takes precedence whenever enough fundamental evidence is
    # supplied. Market/execution analysis remains available as a fallback for
    # uploads without a fundamental data set.
    regime = fundamental_regime or market_regime
    root_key = None
    if regime:
        root_key = "fundamental_stress" if fundamental_regime else "market_stress_regime"
        series[root_key] = regime["series"]
    # Only evaluate relationships that can be displayed as an approved causal route.
    # The former all-pairs scan calculated hundreds of relationships that were
    # discarded before rendering, making the built-in demo needlessly slow.
    tested = []
    fields = list(series)
    field_names = set(fields)
    for source_key, target_key in CAUSE_MAP_LINKS:
        if source_key not in field_names or target_key not in field_names:
            continue
        control_key = next((key for key in fields if key not in (source_key, target_key, "strategy_loss", "pnl")), None)
        control = series[control_key] if control_key else [0.0] * len(records)
        candidate = edge(label_for(source_key), series[source_key], label_for(target_key), series[target_key], control, interval)
        candidate["source_key"], candidate["target_key"] = source_key, target_key
        candidate["score"] = round(abs(candidate["partial"]) * abs(candidate["lag_correlation"]) * candidate["confidence"], 3)
        candidate["explanation"] = explain_edge(source_key, target_key, candidate["confidence"])
        candidate["evidence_detail"] = evidence_detail(source_key, target_key, series[source_key], series[target_key])
        tested.append(candidate)
    apply_fdr_correction(tested)
    tested_count = len(tested)
    tested = [candidate for candidate in tested if candidate["fdr_significant"] or candidate["source_key"] == root_key]
    # The displayed graph is a constrained hypothesis chain. This prevents the
    # UI from turning every significant pairwise correlation into a false
    # directional claim such as "price caused loss".
    cause_map = [item for item in tested if (item["source_key"], item["target_key"]) in CAUSE_MAP_LINKS]
    root_paths = sorted((item for item in cause_map if item["source_key"] == root_key), key=lambda item: item["score"], reverse=True) if root_key else []
    if root_key:
        for candidate in tested:
            if candidate["source_key"] == root_key:
                candidate["evidence_kind"] = "Derived regime membership"
    # Keep non-map, statistically retained direct loss relationships available
    # as secondary leads, but do not draw them as causal arrows.
    secondary = sorted(
        (item for item in tested if item["target_key"] == "strategy_loss" and item not in cause_map),
        key=lambda item: item["score"], reverse=True,
    )[:5]
    edges = cause_map + secondary
    used_keys = {"strategy_loss"}
    for candidate in edges:
        used_keys.update((candidate["source_key"], candidate["target_key"]))
    explanation_paths = cause_map
    high_volatility = [pnl[index] for index, value in enumerate(volatility) if value >= median(volatility)]
    low_volatility = [pnl[index] for index, value in enumerate(volatility) if value < median(volatility)]
    change_series = series.get("fundamental_stress") or series.get("stock_decline") or slippage
    change_label = "Fundamental thesis shift" if fundamental_regime else "Market / execution shift"
    root_causes = root_cause_candidates(data, timestamps, pnl)
    explanation_blocks = dynamic_explanation_blocks(root_causes, cause_map, root_key)
    discovered_patterns = pattern_discovery(data, fundamental_regime, market_regime, lineage_regime)
    return {
        "records": len(records), "summary": {
            "pnl": round(sum(pnl), 2), "pnl_zscore": round(z_score(pnl), 2), "spread_zscore": round(z_score(spread), 2),
            "change_point": detect_change(change_series, timestamps), "change_label": change_label,
            "high_volatility_mean_pnl": round(mean(high_volatility), 2) if high_volatility else None,
            "low_volatility_mean_pnl": round(mean(low_volatility), 2) if low_volatility else None,
            "expected_pnl": round(sum(data["expected_pnl"]), 2) if "expected_pnl" in data else None,
            "implementation_shortfall": round(sum(data["implementation_shortfall"]), 2) if "implementation_shortfall" in data else None,
        },
        "nodes": [{"id": key, "label": label_for(key), "value": f"z = {z_score(series[key]):+.1f}"} for key in used_keys if key != "strategy_loss"] + [{"id": "strategy_loss", "label": "Strategy loss", "value": f"${sum(pnl):,.0f}"}],
        "edges": edges, "explanation_paths": explanation_paths, "explanation_blocks": explanation_blocks, "secondary_leads": secondary,
        "fundamental_domains": fundamental_fault_domains(records, data),
        "alpha_domains": alpha_debugger_domains(records, data),
        "fault_domains": implementation_fault_domains(records, data),
        "basket": basket_summary(records),
        "topic_levels": {label_for(key): causal_level(key) for key in used_keys}, "tested_relationships": tested_count, "fdr_retained_relationships": len(tested),
        "driver_attribution": driver_attribution(data, pnl),
        "pattern_discovery": discovered_patterns,
        "confirmation_plan": confirmation_plan(data, root_key),
        "root_causes": root_causes,
        "root_hypothesis": {
            "label": label_for(root_key) if root_key else "No upstream pattern inferred",
            "confidence": regime["confidence"] if regime else None,
            "features": regime["features"] if regime else [],
            "stress_share": regime["stress_share"] if regime else None,
            "path_count": len(root_paths),
        }, "warnings": [
            "Correlation and lag support a hypothesis; they do not prove causation.",
            "Results can be distorted by omitted variables, multiple testing, and poor timestamp alignment.",
        ],
    }


SAFE_BUILTINS = {"abs": abs, "min": min, "max": max, "sum": sum, "round": round, "float": float, "int": int, "len": len}


def replay(source, bars, parameters=None):
    """Replay a deliberately small, deterministic Python strategy contract.

    Uploaded code must define on_bar(bar, state) and return a target position in [-1, 1].
    This is a compatibility prototype, not a secure sandbox for arbitrary code.
    """
    tree = ast.parse(source, mode="exec")
    prohibited = (ast.Import, ast.ImportFrom, ast.With, ast.Try, ast.ClassDef, ast.Lambda)
    if any(isinstance(node, prohibited) for node in ast.walk(tree)):
        raise ValueError("Replay supports deterministic, dependency-free Python only (no imports, classes, or file/network access).")
    scope = {"__builtins__": SAFE_BUILTINS}
    exec(compile(tree, "uploaded_strategy.py", "exec"), scope, scope)
    function = scope.get("on_bar")
    if not callable(function):
        raise ValueError("Strategy must define: on_bar(bar, state) -> target position")
    parameters = parameters or {}
    notional = float(parameters.get("notional", 1_000_000))
    cost_multiplier = float(parameters.get("cost_multiplier", 1.0))
    state, previous_target, total_pnl, output = {"params": parameters}, 0.0, 0.0, []
    for bar in bars:
        target = float(function(dict(bar), state))
        if not -1 <= target <= 1:
            raise ValueError("on_bar must return a position between -1 and 1.")
        realised = previous_target * float(bar["return"]) * notional
        cost = abs(target - previous_target) * float(bar["spread_bps"]) * (notional / 10_000) * cost_multiplier
        total_pnl += realised - cost
        output.append({"timestamp": bar["timestamp"], "target": target, "pnl": round(realised - cost, 2), "equity": round(total_pnl, 2)})
        previous_target = target
    return {"bars_replayed": len(output), "total_pnl": round(total_pnl, 2), "series": output, "parameters": parameters}


def run_demo(parameters):
    records = synthetic_dataset()
    source = (ROOT / "example_strategy.py").read_text()
    replay_result = replay(source, records, parameters)
    replayed_records = []
    for bar, outcome in zip(records, replay_result["series"]):
        replayed = dict(bar)
        replayed["pnl"] = outcome["pnl"]
        replayed["equity"] = outcome["equity"]
        replayed_records.append(replayed)
    analysis = analyse(replayed_records)
    investigation_id = STORE.save("Synthetic strategy replay", parameters, analysis["summary"], replay_result)
    return {"records": replayed_records, "replay": replay_result, "analysis": analysis, "investigation_id": investigation_id}


class Handler(SimpleHTTPRequestHandler):
    def do_GET(self):
        parsed_url = urlparse(self.path)
        query = parse_qs(parsed_url.query)
        if parsed_url.path == "/api/flight-recorder/status":
            strategy_id = query.get("strategy_id", [None])[0]
            self.respond({"status": STORE.flight_status(strategy_id)})
            return
        if parsed_url.path == "/api/flight-recorder/strategies":
            self.respond({"strategies": STORE.flight_strategies()})
            return
        if parsed_url.path == "/api/flight-recorder/evidence":
            strategy_id = query.get("strategy_id", [None])[0]
            if not strategy_id:
                self.respond({"error": "strategy_id is required."}, 400)
                return
            stored = STORE.flight_events(strategy_id)
            evidence = flight_events_to_evidence(stored)
            if not evidence:
                self.respond({"error": "No lifecycle evidence was recorded for this strategy."}, 404)
                return
            as_of = evidence[-1].get("timestamp")
            snap = make_snapshot(evidence, as_of, "flight-recorder")
            ledger = ledger_for_records(evidence)
            receipts = [assess_ai_decision(row) for row in evidence if row.get("kind") == "decision"]
            self.respond({
                "strategy_id": strategy_id,
                "events": evidence,
                "outcome_records": typed_events_to_outcome_records(evidence),
                "snapshot_id": snap["snapshot_id"],
                "ledger": ledger,
                "ai_forensics": receipts,
                "strategy_profile": inspect_strategy(evidence),
                "detected_decision": detected_decision(evidence),
                "status": STORE.flight_status(strategy_id),
            })
            return
        if self.path == "/healthz":
            # Used by hosting providers to confirm that the Python API is ready.
            self.respond({"status": "ok"})
            return
        if self.path == "/api/demo":
            self.respond({"records": synthetic_dataset()})
            return
        if self.path == "/api/synthetic-scenarios":
            self.respond({"scenarios": scenario_catalog()})
            return
        if self.path == "/api/sample/full-product":
            self.respond({"records": load_sample("full-product"), "label": "full_product_demo.csv"})
            return
        if self.path == "/api/history":
            self.respond({"investigations": STORE.recent()})
            return
        super().do_GET()

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            payload = json.loads(self.rfile.read(length))
            if self.path == "/api/evidence-bundle/validate":
                bundle = validate_event_bundle(payload)
                bundle["ledger"] = ledger_for_records(bundle["events"])
                bundle["ai_forensics"] = [assess_ai_decision(event) for event in bundle["events"] if event.get("kind") == "decision"]
                self.respond(bundle)
            elif self.path == "/api/incident-bundle/validate":
                self.respond({"receipt": validate_incident_bundle(payload)})
            elif self.path == "/api/incident-command":
                records = payload.get("records") or []
                snap = make_snapshot(records, payload.get("as_of") or (records[-1].get("timestamp") if records else ""), payload.get("source") or "incident-command")
                self.respond(incident_command(records, payload.get("label"), snap, STORE.recent()))
            elif self.path == "/api/reproducibility-receipt":
                records = payload.get("records") or []
                snap = make_snapshot(records, payload.get("as_of") or (records[-1].get("timestamp") if records else ""), payload.get("source") or "receipt")
                self.respond(make_reproducibility_receipt(snap["snapshot_id"], {"records": len(records)}, {"source": snap["source"]}))
            elif self.path == "/api/incident-bundle/attribution":
                self.respond({"attribution": attribute_pnl(payload.get("rows"))})
            elif self.path == "/api/investigation/replay":
                snapshot = reconstruct_as_of(payload.get("records") or [], payload.get("as_of"))
                snap = make_snapshot(snapshot, payload.get("as_of"), "replay")
                ledger = ledger_for_records(snapshot)
                ai_receipts = [assess_ai_decision(row) for row in snapshot if row.get("kind") == "decision"]
                profile = inspect_strategy(snapshot)
                imported_decision = detected_decision(snapshot)
                analysis_records = snapshot
                if any(row.get("kind") for row in snapshot) and not all(row.get("pnl") not in (None, "") for row in snapshot):
                    analysis_records = typed_events_to_outcome_records(snapshot)
                if len(analysis_records) < 50:
                    # A decision receipt is useful with a single retained decision.
                    # Statistical diagnosis remains unavailable until 50 observations.
                    self.respond({"as_of": payload.get("as_of"), "records": len(snapshot), "evidence_ready": True, "analysis_ready": False, "snapshot_id": snap["snapshot_id"], "ledger": ledger, "ai_forensics": ai_receipts, "strategy_profile": profile, "detected_decision": imported_decision, "reason": "Fewer than 50 observations: showing the retained decision receipt without statistical diagnosis."})
                else:
                    analysis = analyse(analysis_records)
                    analysis["explanation_blocks"] = build_evidence_flow(analysis_records, analysis)
                    analysis["snapshot_id"] = snap["snapshot_id"]
                    graph = build_investigation_graph(analysis_records, analysis)
                    graph["snapshot_id"] = snap["snapshot_id"]
                    self.respond({"as_of": payload.get("as_of"), "records": len(snapshot), "evidence_ready": True, "analysis_ready": True, "snapshot_id": snap["snapshot_id"], "analysis": analysis, "graph": graph, "ledger": ledger, "ai_forensics": ai_receipts, "strategy_profile": profile, "detected_decision": imported_decision})
            elif self.path == "/api/investigation/graph":
                records = payload.get("records")
                self.respond({"graph": build_investigation_graph(records, payload.get("analysis") or {})})
            elif self.path == "/api/analyse":
                analysis = analyse(payload["records"])
                analysis["explanation_blocks"] = build_evidence_flow(payload["records"], analysis)
                analysis["strategy_profile"] = inspect_strategy(payload["records"])
                investigation_id = STORE.save(payload.get("label", "Uploaded data diagnosis"), {}, analysis["summary"])
                analysis["investigation_id"] = investigation_id
                self.respond(analysis)
            elif self.path == "/api/analyse-bundle":
                market_rows = parse_csv_text(payload["market_csv"], "Market")
                strategy_rows = parse_csv_text(payload["strategy_csv"], "Strategy")
                records, alignment = align_market_and_strategy(market_rows, strategy_rows, payload.get("max_gap_minutes", 5))
                analysis = analyse(records)
                investigation_id = STORE.save(payload.get("label", "Aligned market and strategy diagnosis"), {"alignment": alignment}, analysis["summary"])
                analysis["investigation_id"] = investigation_id
                self.respond({"analysis": analysis, "records": records, "alignment": alignment})
            elif self.path == "/api/replay":
                self.respond(replay(payload["source"], payload["bars"], payload.get("parameters")))
            elif self.path == "/api/demo-run":
                self.respond(run_demo(payload.get("parameters", {})))
            elif self.path == "/api/review":
                self.respond({"review_id": STORE.save_review(payload["source"], payload["target"], payload["decision"])})
            elif self.path == "/api/flight-recorder/events":
                events = payload.get("events")
                if not isinstance(events, list) or not events:
                    raise ValueError("Provide a non-empty events array.")
                if len(events) > 5_000:
                    raise ValueError("Send at most 5,000 events per request.")
                normalised = [normalise_flight_event(event) for event in events]
                strategy_ids = {event["strategy_id"] for event in normalised}
                if len(strategy_ids) != 1:
                    raise ValueError("Each request must contain events for one strategy_id.")
                outcome = STORE.append_flight_events(normalised)
                self.respond({"strategy_id": normalised[0]["strategy_id"], **outcome, "status": STORE.flight_status(normalised[0]["strategy_id"])}, 201)
            elif self.path == "/api/flight-recorder/demo":
                events = demo_flight_events()
                outcome = STORE.append_flight_events(events)
                strategy_id = events[0]["strategy_id"]
                records = flight_events_to_records(STORE.flight_events(strategy_id))
                analysis = analyse(records)
                investigation_id = STORE.save("Flight recorder demo incident", {"strategy_id": strategy_id, "source": "local flight recorder"}, analysis["summary"])
                self.respond({"strategy_id": strategy_id, **outcome, "status": STORE.flight_status(strategy_id), "records": records, "analysis": analysis, "investigation_id": investigation_id})
            elif self.path == "/api/flight-recorder/analyse":
                strategy_id = str(payload.get("strategy_id", "")).strip()
                if not strategy_id:
                    raise ValueError("strategy_id is required.")
                start, end = payload.get("start"), payload.get("end")
                if start:
                    start = parse_timestamp(start, "Incident start").isoformat()
                if end:
                    end = parse_timestamp(end, "Incident end").isoformat()
                events = STORE.flight_events(strategy_id, start, end)
                records = flight_events_to_records(events)
                analysis = analyse(records)
                investigation_id = STORE.save(f"Flight recorder incident: {strategy_id}", {"strategy_id": strategy_id, "start": start, "end": end, "event_count": len(events)}, analysis["summary"])
                self.respond({"strategy_id": strategy_id, "events": len(events), "records": records, "analysis": analysis, "status": STORE.flight_status(strategy_id), "investigation_id": investigation_id})
            else:
                self.respond({"error": "Unknown endpoint"}, 404)
        except (ValueError, KeyError, SyntaxError) as error:
            self.respond({"error": str(error)}, 400)
        except Exception:
            self.respond({"error": "Unexpected analysis error. Check your input data and strategy contract."}, 500)

    def respond(self, payload, status=200):
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    import os
    host, port = os.environ.get("HOST", "127.0.0.1"), int(os.environ.get("PORT", "8000"))
    print(f"Quant Doctor running at http://{host}:{port}")
    ThreadingHTTPServer((host, port), Handler).serve_forever()
