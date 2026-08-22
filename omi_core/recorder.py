"""Framework-neutral, read-only flight recorder for trading strategies.

The recorder observes a strategy call and emits immutable evidence. It never
submits, changes, or cancels an order.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from functools import wraps
import hashlib
import inspect
import json
from pathlib import Path
from collections.abc import Iterator
from typing import Any, Callable, Mapping
from urllib.request import Request, urlopen


LIFECYCLE_EVENT_TYPES = {
    "observation": "fundamental_snapshot",
    "decision": "strategy_decision",
    "target": "portfolio_target",
    "fill": "fill",
    "position": "position_snapshot",
    "pnl": "pnl_mark",
}
VALID_ACTIONS = {"BUY", "SELL", "HOLD"}
ROUTING_FIELDS = {"timestamp", "available_at", "symbol", "kind", "event_id", "parent_id"}


class AccessTrackingMapping(Mapping[str, Any]):
    """Read-only mapping that remembers which feature keys a strategy reads."""

    def __init__(self, values: Mapping[str, Any]):
        self._values = values
        self.accessed: set[str] = set()

    def __getitem__(self, key: str) -> Any:
        self.accessed.add(key)
        return self._values[key]

    def __iter__(self) -> Iterator[str]:
        # Iterating a mapping exposes every key to the strategy.
        self.accessed.update(self._values)
        return iter(self._values)

    def __len__(self) -> int:
        return len(self._values)

    def snapshot(self) -> dict[str, Any]:
        return {key: self._values[key] for key in self._values if key in self.accessed}


def _json_ready(value: Any) -> Any:
    """Return deterministic JSON data or reject an unsafe opaque object."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, datetime):
        return _timestamp(value)
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_ready(item) for item in value]
    if hasattr(value, "item") and callable(value.item):
        return _json_ready(value.item())
    raise TypeError(f"OMI cannot fingerprint input value of type {type(value).__name__}; convert it to JSON data first.")


def _canonical(value: Any) -> str:
    return json.dumps(_json_ready(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _hash(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _timestamp(value: Any) -> str:
    if value is None:
        parsed = datetime.now(timezone.utc)
    elif isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as error:
            raise ValueError(f"Invalid ISO-8601 timestamp: {value!r}") from error
    else:
        raise TypeError("timestamp must be an ISO-8601 string or datetime")
    if parsed.tzinfo is None:
        raise ValueError("OMI recorder timestamps must include a timezone offset")
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def callable_fingerprint(function: Callable[..., Any]) -> str:
    """Fingerprint source when available, otherwise stable Python bytecode."""
    try:
        material = {"source": inspect.getsource(function), "module": function.__module__, "name": function.__qualname__}
    except (OSError, TypeError):
        code = getattr(function, "__code__", None)
        material = {
            "module": getattr(function, "__module__", None),
            "name": getattr(function, "__qualname__", getattr(function, "__name__", type(function).__name__)),
            "bytecode": code.co_code.hex() if code else None,
            "constants": [repr(item) for item in code.co_consts] if code else None,
        }
    return _hash(material)


class MemorySink:
    """Collect evidence in memory for embedding, tests, or later export."""

    def __init__(self):
        self.events: list[dict[str, Any]] = []

    def emit(self, events: list[dict[str, Any]]) -> None:
        self.events.extend(_json_ready(events))


class JsonlSink:
    """Append one immutable JSON event per line."""

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def emit(self, events: list[dict[str, Any]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            for event in events:
                handle.write(_canonical(event) + "\n")


class HttpSink:
    """Send evidence to OMI's local append-only flight-recorder endpoint."""

    def __init__(self, base_url: str = "http://127.0.0.1:8000", timeout: float = 3.0):
        self.url = base_url.rstrip("/") + "/api/flight-recorder/events"
        self.timeout = timeout

    @staticmethod
    def _flight_event(event: Mapping[str, Any]) -> dict[str, Any]:
        data = {key: value for key, value in event.items() if key not in {"strategy_id", "timestamp", "symbol"}}
        return {
            "event_id": event["event_id"],
            "strategy_id": event["strategy_id"],
            "event_type": LIFECYCLE_EVENT_TYPES[event["kind"]],
            "timestamp": event["timestamp"],
            "symbol": event.get("symbol"),
            "data": data,
        }

    def emit(self, events: list[dict[str, Any]]) -> None:
        body = _canonical({"events": [self._flight_event(event) for event in events]}).encode("utf-8")
        request = Request(self.url, data=body, headers={"Content-Type": "application/json"}, method="POST")
        with urlopen(request, timeout=self.timeout) as response:
            if response.status not in (200, 201):
                raise RuntimeError(f"OMI collector rejected evidence with HTTP {response.status}")


class CompositeSink:
    """Write the same evidence to multiple sinks."""

    def __init__(self, *sinks: Any):
        self.sinks = sinks

    def emit(self, events: list[dict[str, Any]]) -> None:
        for sink in self.sinks:
            sink.emit(events)


class ExecutionAdapter:
    """Map broker/OMS field names into OMI fill, position, and P&L facts."""

    def __init__(self, **field_map: str):
        self.fields = {
            "timestamp": "timestamp",
            "fill_quantity": "fill_quantity",
            "fill_price": "price",
            "position_quantity": "position_quantity",
            "pnl": "pnl",
            **field_map,
        }

    def _value(self, payload: Mapping[str, Any], name: str) -> Any:
        field_name = self.fields[name]
        if field_name not in payload or payload[field_name] in (None, ""):
            raise ValueError(f"Execution payload is missing mapped {name} field {field_name!r}")
        return payload[field_name]

    def _details(self, payload: Mapping[str, Any], used: tuple[str, ...]) -> dict[str, Any]:
        consumed = {self.fields[name] for name in used}
        return {str(key): value for key, value in payload.items() if key not in consumed}

    def record_fill(self, receipt: "DecisionReceipt", payload: Mapping[str, Any]) -> "DecisionReceipt":
        used = ("timestamp", "fill_quantity", "fill_price")
        return receipt.record_fill(
            quantity=self._value(payload, "fill_quantity"),
            price=self._value(payload, "fill_price"),
            timestamp=self._value(payload, "timestamp"),
            **self._details(payload, used),
        )

    def record_position(self, receipt: "DecisionReceipt", payload: Mapping[str, Any]) -> "DecisionReceipt":
        used = ("timestamp", "position_quantity")
        return receipt.record_position(
            quantity=self._value(payload, "position_quantity"),
            timestamp=self._value(payload, "timestamp"),
            **self._details(payload, used),
        )

    def record_pnl(self, receipt: "DecisionReceipt", payload: Mapping[str, Any]) -> "DecisionReceipt":
        used = ("timestamp", "pnl")
        return receipt.record_pnl(
            pnl=self._value(payload, "pnl"),
            timestamp=self._value(payload, "timestamp"),
            **self._details(payload, used),
        )


@dataclass
class DecisionReceipt:
    """Handle used to append execution and outcome facts to one decision."""

    recorder: "StrategyRecorder" = field(repr=False)
    symbol: str
    timestamp: str
    result: Any
    observation_id: str
    decision_id: str
    target_id: str | None
    events: list[dict[str, Any]] = field(default_factory=list)
    fill_id: str | None = None
    position_id: str | None = None

    def record_fill(self, *, quantity: float, price: float, timestamp: Any, **details: Any) -> "DecisionReceipt":
        if not self.target_id:
            raise ValueError("Cannot link a fill because the strategy result did not record a target")
        payload = {"fill_quantity": quantity, "price": price, **details}
        event = self.recorder._event("fill", timestamp, self.symbol, self.target_id, payload)
        self.fill_id = event["event_id"]
        self.events.append(event)
        self.recorder._emit([event])
        return self

    def record_position(self, *, quantity: float, timestamp: Any, **details: Any) -> "DecisionReceipt":
        if not self.fill_id:
            raise ValueError("Cannot link a position before recording its fill")
        event = self.recorder._event("position", timestamp, self.symbol, self.fill_id, {"position_quantity": quantity, **details})
        self.position_id = event["event_id"]
        self.events.append(event)
        self.recorder._emit([event])
        return self

    def record_pnl(self, *, pnl: float, timestamp: Any, **details: Any) -> "DecisionReceipt":
        if not self.position_id:
            raise ValueError("Cannot link P&L before recording the resulting position")
        event = self.recorder._event("pnl", timestamp, self.symbol, self.position_id, {"pnl": pnl, **details})
        self.events.append(event)
        self.recorder._emit([event])
        return self


class StrategyRecorder:
    """Capture point-in-time evidence around an otherwise unchanged strategy."""

    def __init__(
        self,
        strategy_id: str,
        *,
        strategy_version: str | None = None,
        model_version: str | None = None,
        parameters: Mapping[str, Any] | None = None,
        sink: Any | None = None,
    ):
        if not strategy_id or not all(character.isalnum() or character in "_.-" for character in strategy_id):
            raise ValueError("strategy_id must use letters, numbers, dots, hyphens, or underscores")
        self.strategy_id = strategy_id
        self.strategy_version = strategy_version
        self.model_version = model_version
        self.parameters = _json_ready(parameters or {})
        self.parameter_hash = _hash(self.parameters)
        self.sink = sink or MemorySink()
        self.events: list[dict[str, Any]] = []
        self._latest_by_symbol: dict[str, DecisionReceipt] = {}

    def _event(self, kind: str, timestamp: Any, symbol: str, parent_id: str | None, payload: Mapping[str, Any]) -> dict[str, Any]:
        event_time = _timestamp(timestamp)
        clean_payload = _json_ready(payload)
        base = {
            "kind": kind,
            "parent_id": parent_id,
            "timestamp": event_time,
            "available_at": clean_payload.get("available_at", event_time),
            "strategy_id": self.strategy_id,
            "strategy_version": self.strategy_version,
            "parameter_hash": self.parameter_hash,
            "symbol": str(symbol).upper(),
            **clean_payload,
        }
        if _timestamp(base["available_at"]) > event_time:
            raise ValueError(f"{kind} evidence available_at cannot be later than its timestamp")
        digest = _hash(base)
        return {**base, "event_id": f"{kind}-{digest[:20]}", "raw_artifact_hash": digest}

    def _emit(self, events: list[dict[str, Any]]) -> None:
        self.events.extend(events)
        self.sink.emit(events)

    @staticmethod
    def _result_mapping(result: Any, adapter: Callable[[Any], Mapping[str, Any]] | None) -> dict[str, Any]:
        if adapter:
            mapped = adapter(result)
        elif isinstance(result, str):
            mapped = {"action": result}
        elif isinstance(result, Mapping):
            mapped = result
        else:
            fields = ("action", "decision_reason", "reason", "target_quantity", "target_position", "target_weight", "confidence", "score", "reason_codes")
            mapped = {name: getattr(result, name) for name in fields if hasattr(result, name)}
        if not isinstance(mapped, Mapping):
            raise TypeError("Decision adapter must return a mapping")
        return _json_ready(mapped)

    def capture_decision(
        self,
        function: Callable[[Mapping[str, Any]], Any],
        inputs: Mapping[str, Any],
        *,
        symbol: str,
        timestamp: Any,
        available_at: Any | None = None,
        result_adapter: Callable[[Any], Mapping[str, Any]] | None = None,
        callable_identity: Callable[..., Any] | None = None,
        input_provenance: Mapping[str, Mapping[str, Any]] | None = None,
    ) -> DecisionReceipt:
        """Call a strategy once and capture its inputs, output, and identity."""
        if not isinstance(inputs, Mapping):
            raise TypeError("inputs must be a mapping of feature names to values")
        decision_time = _timestamp(timestamp)
        input_time = _timestamp(available_at or decision_time)
        if input_time > decision_time:
            raise ValueError("Decision inputs cannot be available after the decision timestamp")
        identity = callable_identity or function
        code_hash = callable_fingerprint(identity)
        tracked_inputs = AccessTrackingMapping(inputs)
        result = function(tracked_inputs)
        # A strategy that accepts the mapping but delegates the work may leave
        # no observable key access. In that case retain the supplied snapshot
        # and label it honestly as the call boundary rather than dropping it.
        used_inputs = tracked_inputs.snapshot() or dict(inputs)
        feature_values = _json_ready(used_inputs)
        used_provenance = {
            field: details for field, details in (input_provenance or {}).items() if field in feature_values
        }
        feature_snapshot_id = f"features-{_hash({'symbol': symbol, 'available_at': input_time, 'values': feature_values})[:20]}"
        observation_payload = {
            "available_at": input_time,
            "feature_snapshot_id": feature_snapshot_id,
            "input_hash": _hash(feature_values),
            "input_provenance": used_provenance,
            **{key: value for key, value in feature_values.items() if key not in ROUTING_FIELDS},
        }
        observation = self._event("observation", decision_time, symbol, None, observation_payload)
        self._emit([observation])
        output = self._result_mapping(result, result_adapter)
        action = str(output.get("action", "")).upper()
        if action not in VALID_ACTIONS:
            raise ValueError("Recorded strategy result must contain action BUY, SELL, or HOLD")
        reason = output.get("decision_reason") or output.get("reason")
        derived_model_version = self.model_version or f"callable-sha256:{code_hash[:12]}"
        decision_payload = {
            **output,
            "action": action,
            "decision_reason": reason,
            "decision_timestamp": decision_time,
            "available_at": input_time,
            "model_version": derived_model_version,
            "model_hash": code_hash,
            "code_hash": code_hash,
            "feature_snapshot_id": feature_snapshot_id,
            "feature_values": feature_values,
            "input_provenance": used_provenance,
        }
        decision = self._event("decision", decision_time, symbol, observation["event_id"], decision_payload)
        events = [observation, decision]
        target_fields = {key: output[key] for key in ("target_quantity", "target_position", "target_weight") if output.get(key) is not None}
        target = self._event("target", decision_time, symbol, decision["event_id"], target_fields) if target_fields else None
        if target:
            events.append(target)
        # Observation was emitted before the call; emit only the new records.
        self._emit(events[1:])
        receipt = DecisionReceipt(
            recorder=self,
            symbol=str(symbol).upper(),
            timestamp=decision_time,
            result=result,
            observation_id=observation["event_id"],
            decision_id=decision["event_id"],
            target_id=target["event_id"] if target else None,
            events=list(events),
        )
        self._latest_by_symbol[receipt.symbol] = receipt
        return receipt

    def capture_connected_decision(
        self,
        function: Callable[[Mapping[str, Any]], Any],
        snapshot: Any,
        *,
        symbol: str | None = None,
        result_adapter: Callable[[Any], Mapping[str, Any]] | None = None,
    ) -> DecisionReceipt:
        """Capture a decision from a ConnectorHub ConnectedSnapshot."""
        values = getattr(snapshot, "values", None)
        provenance = getattr(snapshot, "provenance", None)
        decision_time = getattr(snapshot, "decision_time", None)
        snapshot_symbol = symbol or getattr(snapshot, "symbol", None)
        if not isinstance(values, Mapping) or not isinstance(provenance, Mapping) or not decision_time or not snapshot_symbol:
            raise TypeError("snapshot must be a ConnectedSnapshot with a symbol and decision_time")
        available_times = [details.get("available_at") for details in provenance.values() if details.get("available_at")]
        available_at = max(available_times) if available_times else decision_time
        return self.capture_decision(
            function,
            values,
            symbol=snapshot_symbol,
            timestamp=decision_time,
            available_at=available_at,
            result_adapter=result_adapter,
            input_provenance=provenance,
        )

    def latest_receipt(self, symbol: str) -> DecisionReceipt | None:
        return self._latest_by_symbol.get(str(symbol).upper())

    def instrument(
        self,
        *,
        symbol_field: str = "symbol",
        timestamp_field: str = "timestamp",
        available_at_field: str = "available_at",
        input_selector: Callable[..., Mapping[str, Any]] | None = None,
        result_adapter: Callable[[Any], Mapping[str, Any]] | None = None,
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """Decorate a strategy function while preserving its return value."""
        def decorator(function: Callable[..., Any]) -> Callable[..., Any]:
            @wraps(function)
            def wrapped(*args: Any, **kwargs: Any) -> Any:
                inputs = input_selector(*args, **kwargs) if input_selector else (args[0] if args else kwargs.get("inputs"))
                if not isinstance(inputs, Mapping):
                    raise TypeError("Instrumented strategy needs mapping inputs or an input_selector")
                symbol = inputs.get(symbol_field)
                timestamp = inputs.get(timestamp_field)
                if not symbol or not timestamp:
                    raise ValueError(f"Instrumented inputs must contain {symbol_field!r} and {timestamp_field!r}")
                invoke = (lambda observed: function(observed, *args[1:], **kwargs)) if not input_selector and args else (lambda _: function(*args, **kwargs))
                receipt = self.capture_decision(
                    invoke,
                    inputs,
                    symbol=str(symbol),
                    timestamp=timestamp,
                    available_at=inputs.get(available_at_field) or timestamp,
                    result_adapter=result_adapter,
                    callable_identity=function,
                )
                return receipt.result
            return wrapped
        return decorator

    def evidence_bundle(self) -> dict[str, Any]:
        return {
            "schema_version": "omi-evidence/v1",
            "strategy_id": self.strategy_id,
            "strategy_version": self.strategy_version,
            "parameter_hash": self.parameter_hash,
            "events": list(self.events),
        }
