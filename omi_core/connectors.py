"""Read-only connector contracts for point-in-time strategy evidence."""
from __future__ import annotations

from abc import ABC, abstractmethod
import csv
from dataclasses import dataclass
from datetime import datetime, timezone
import io
import json
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .recorder import _hash, _json_ready, _timestamp


def _path_value(payload: Any, path: str) -> Any:
    value = payload
    for part in path.split(".") if path else ():
        if isinstance(value, Mapping):
            value = value[part]
        elif isinstance(value, list):
            value = value[int(part)]
        else:
            raise KeyError(f"Cannot select {path!r}; {part!r} is not inside an object or list")
    return value


class FieldMapper:
    """Rename/nest external fields and optionally normalize their values."""

    def __init__(self, fields: Mapping[str, str] | None = None, transforms: Mapping[str, Callable[[Any], Any]] | None = None):
        self.fields = dict(fields or {})
        self.transforms = dict(transforms or {})

    def apply(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, Mapping):
            raise TypeError("A connector field mapper requires an object payload")
        mapped = dict(payload) if not self.fields else {target: _path_value(payload, source) for target, source in self.fields.items()}
        for field, transform in self.transforms.items():
            if field in mapped:
                mapped[field] = transform(mapped[field])
        return _json_ready(mapped)


@dataclass(frozen=True)
class SourceEnvelope:
    """One immutable source snapshot and its availability provenance."""

    source_id: str
    values: Mapping[str, Any]
    observed_at: str
    available_at: str
    retrieved_at: str
    version: str | None
    raw_hash: str
    connector_type: str

    def provenance(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "observed_at": self.observed_at,
            "available_at": self.available_at,
            "retrieved_at": self.retrieved_at,
            "version": self.version,
            "raw_hash": self.raw_hash,
            "connector_type": self.connector_type,
        }


class EvidenceConnector(ABC):
    """Minimal interface implemented by any data/API adapter."""

    source_id: str

    @abstractmethod
    def read(self, *, symbol: str | None = None, as_of: Any | None = None, **context: Any) -> SourceEnvelope:
        raise NotImplementedError


class _EnvelopeFactory:
    def __init__(
        self,
        source_id: str,
        *,
        mapper: FieldMapper | None = None,
        version: str | None = None,
        observed_at_field: str = "timestamp",
        available_at_field: str = "available_at",
    ):
        if not source_id:
            raise ValueError("source_id is required")
        self.source_id = source_id
        self.mapper = mapper or FieldMapper()
        self.version = version
        self.observed_at_field = observed_at_field
        self.available_at_field = available_at_field

    def envelope(self, raw: Mapping[str, Any], connector_type: str) -> SourceEnvelope:
        if not isinstance(raw, Mapping):
            raise TypeError(f"{self.source_id} connector must return an object")
        observed = _path_value(raw, self.observed_at_field) if self.observed_at_field else None
        try:
            available = _path_value(raw, self.available_at_field) if self.available_at_field else None
        except KeyError:
            available = None
        available = available or observed
        if not observed or not available:
            raise ValueError(f"{self.source_id} must provide {self.observed_at_field!r} and {self.available_at_field!r} timestamps")
        values = self.mapper.apply(raw)
        return SourceEnvelope(
            source_id=self.source_id,
            values=values,
            observed_at=_timestamp(observed),
            available_at=_timestamp(available),
            retrieved_at=_timestamp(datetime.now(timezone.utc)),
            version=self.version,
            raw_hash=_hash(raw),
            connector_type=connector_type,
        )


class CallableConnector(EvidenceConnector):
    """Wrap an existing SDK/client function as an OMI evidence source."""

    def __init__(self, source_id: str, fetch: Callable[..., Mapping[str, Any]], **options: Any):
        self.factory = _EnvelopeFactory(source_id, **options)
        self.source_id = source_id
        self.fetch = fetch

    def read(self, *, symbol: str | None = None, as_of: Any | None = None, **context: Any) -> SourceEnvelope:
        raw = self.fetch(symbol=symbol, as_of=as_of, **context)
        return self.factory.envelope(raw, "callable")


class HttpJsonConnector(EvidenceConnector):
    """Read JSON from a GET-only HTTP API; credentials remain in request headers."""

    def __init__(
        self,
        source_id: str,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        selector: str = "",
        query_builder: Callable[..., Mapping[str, Any]] | None = None,
        timeout: float = 5.0,
        **options: Any,
    ):
        if not url.lower().startswith(("http://", "https://")):
            raise ValueError("HTTP connector URL must begin with http:// or https://")
        self.factory = _EnvelopeFactory(source_id, **options)
        self.source_id = source_id
        self.url = url
        self.headers = dict(headers or {})
        self.selector = selector
        self.query_builder = query_builder
        self.timeout = timeout

    def read(self, *, symbol: str | None = None, as_of: Any | None = None, **context: Any) -> SourceEnvelope:
        query = self.query_builder(symbol=symbol, as_of=as_of, **context) if self.query_builder else {}
        url = self.url + (("&" if "?" in self.url else "?") + urlencode(query, doseq=True) if query else "")
        request = Request(url, headers={"Accept": "application/json", **self.headers}, method="GET")
        with urlopen(request, timeout=self.timeout) as response:
            raw_document = json.loads(response.read())
        raw = _path_value(raw_document, self.selector)
        return self.factory.envelope(raw, "http-json")


class FileConnector(EvidenceConnector):
    """Read point-in-time evidence from CSV, JSON, or JSONL."""

    def __init__(self, source_id: str, path: str | Path, **options: Any):
        self.factory = _EnvelopeFactory(source_id, **options)
        self.source_id = source_id
        self.path = Path(path)

    def _rows(self) -> list[Mapping[str, Any]]:
        suffix = self.path.suffix.lower()
        text = self.path.read_text(encoding="utf-8")
        if suffix == ".csv":
            return list(csv.DictReader(io.StringIO(text)))
        if suffix in {".jsonl", ".ndjson"}:
            return [json.loads(line) for line in text.splitlines() if line.strip()]
        if suffix == ".json":
            document = json.loads(text)
            if isinstance(document, list):
                return document
            if isinstance(document, Mapping):
                return [document]
        raise ValueError("FileConnector supports .csv, .json, .jsonl, and .ndjson")

    def read(self, *, symbol: str | None = None, as_of: Any | None = None, **context: Any) -> SourceEnvelope:
        rows = self._rows()
        matching = [row for row in rows if not symbol or str(row.get("symbol", "")).upper() in {"", str(symbol).upper()}]
        if as_of:
            cutoff = _timestamp(as_of)
            matching = [row for row in matching if row.get(self.factory.available_at_field) or row.get(self.factory.observed_at_field)]
            matching = [row for row in matching if _timestamp(row.get(self.factory.available_at_field) or row[self.factory.observed_at_field]) <= cutoff]
        if not matching:
            raise ValueError(f"{self.source_id} has no record available for this symbol and time")
        matching.sort(key=lambda row: _timestamp(row.get(self.factory.available_at_field) or row[self.factory.observed_at_field]))
        return self.factory.envelope(matching[-1], "file")


class ConnectedSnapshot:
    """Merged values plus per-field evidence provenance."""

    def __init__(self, values: Mapping[str, Any], provenance: Mapping[str, Mapping[str, Any]], decision_time: str, symbol: str | None):
        self._values = values
        self.provenance = provenance
        self.decision_time = decision_time
        self.symbol = symbol

    @property
    def values(self) -> Mapping[str, Any]:
        return self._values

    def __getitem__(self, key: str) -> Any:
        return self._values[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._values)

    def __len__(self) -> int:
        return len(self._values)


class ConnectorHub:
    """Merge arbitrary sources into one time-valid decision snapshot."""

    def __init__(self):
        self._connectors: list[tuple[EvidenceConnector, str | None]] = []

    def add(self, connector: EvidenceConnector, *, prefix: str | None = None) -> "ConnectorHub":
        if not isinstance(connector, EvidenceConnector):
            raise TypeError("connector must implement EvidenceConnector")
        self._connectors.append((connector, prefix))
        return self

    def snapshot(self, *, decision_time: Any, symbol: str | None = None, context: Mapping[str, Any] | None = None) -> ConnectedSnapshot:
        cutoff = _timestamp(decision_time)
        values: dict[str, Any] = {}
        provenance: dict[str, Mapping[str, Any]] = {}
        for connector, prefix in self._connectors:
            envelope = connector.read(symbol=symbol, as_of=cutoff, **dict(context or {}))
            if envelope.available_at > cutoff:
                raise ValueError(f"{connector.source_id} returned evidence available after the decision time")
            for field, value in envelope.values.items():
                output_field = f"{prefix}.{field}" if prefix else field
                if output_field in values:
                    raise ValueError(f"Connected sources both produced {output_field!r}; assign a prefix or map one field")
                values[output_field] = value
                provenance[output_field] = envelope.provenance()
        return ConnectedSnapshot(values=_json_ready(values), provenance=_json_ready(provenance), decision_time=cutoff, symbol=str(symbol).upper() if symbol else None)
