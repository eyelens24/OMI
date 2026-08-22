"""Immutable identity for a single point-in-time investigation."""
import hashlib
import json


def make_snapshot(records, as_of, source):
    canonical = json.dumps({"as_of": as_of, "source": source, "records": records}, sort_keys=True, separators=(",", ":"), default=str)
    return {"snapshot_id": hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16], "as_of": as_of, "source": source, "record_count": len(records)}
