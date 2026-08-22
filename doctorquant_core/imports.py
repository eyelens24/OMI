"""Read-only typed-event import validation for Doctor Quant evidence bundles."""
from .ledger import LIFECYCLE


def validate_event_bundle(bundle):
    events = bundle.get("events") if isinstance(bundle, dict) else None
    if not isinstance(events, list):
        raise ValueError("Event bundle requires an events array.")
    accepted, rejected = [], []
    for index, event in enumerate(events):
        if not isinstance(event, dict):
            rejected.append({"index": index, "reason": "event must be an object"}); continue
        if event.get("kind") not in LIFECYCLE:
            rejected.append({"index": index, "reason": "unknown lifecycle kind"}); continue
        if not event.get("event_id") or not event.get("timestamp"):
            rejected.append({"index": index, "reason": "event_id and timestamp are required"}); continue
        accepted.append(dict(event))
    return {"mode": "read-only", "accepted": len(accepted), "rejected": rejected, "events": accepted}
