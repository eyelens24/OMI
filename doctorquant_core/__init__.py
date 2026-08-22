"""Doctor Quant forensic core: deterministic, local-only evidence analysis."""

from .recorder import CompositeSink, DecisionReceipt, ExecutionAdapter, HttpSink, JsonlSink, MemorySink, StrategyRecorder
from .connectors import CallableConnector, ConnectedSnapshot, ConnectorHub, EvidenceConnector, FieldMapper, FileConnector, HttpJsonConnector, SourceEnvelope

__all__ = [
    "CallableConnector", "CompositeSink", "ConnectedSnapshot", "ConnectorHub", "DecisionReceipt",
    "EvidenceConnector", "ExecutionAdapter", "FieldMapper", "FileConnector", "HttpJsonConnector",
    "HttpSink", "JsonlSink", "MemorySink", "SourceEnvelope", "StrategyRecorder",
]
