# Incident Bundle v1

Doctor Quant is a local forensic system for systematic-investing incidents. An incident bundle is the portable evidence package used to validate what can be investigated before any causal hypothesis is displayed.

## Validation endpoint

```text
POST /api/incident-bundle/validate
Content-Type: application/json
```

The endpoint is read-only: it does not save an investigation, place orders, or modify a broker.

## Minimal assessable bundle

```json
{
  "manifest": {
    "schema_version": "incident-bundle/v1",
    "incident_id": "loss-2026-08-21-aapl",
    "strategy_version": "strategy-2.3.1",
    "parameter_hash": "immutable-config-hash"
  },
  "tables": {
    "decisions": [{
      "event_id": "decision-1",
      "event_timestamp": "2026-08-21T14:00:00+00:00",
      "available_at": "2026-08-21T13:59:00+00:00",
      "symbol_id": "US0378331005",
      "action": "BUY",
      "target_weight": 0.05,
      "alpha_score": 0.72
    }],
    "pnl": [{
      "event_id": "pnl-1",
      "event_timestamp": "2026-08-21T20:00:00+00:00",
      "symbol_id": "US0378331005",
      "pnl": -1250.0
    }]
  }
}
```

`available_at` must not be later than the decision's `event_timestamp`. Doctor Quant rejects future-available observations to prevent lookahead bias.

## Optional attribution evidence

Add `fills`, `positions`, `market_data`, `fundamentals`, and `data_lineage` tables to unlock their respective attribution checks. Missing tables are explicit evidence gaps, never silently interpreted as a negative finding.

For a deterministic P&L waterfall, submit explicit components:

```text
POST /api/incident-bundle/attribution
{"rows":[{"pnl":-100,"selection_pnl":-60,"exposure_pnl":-20,"execution_pnl":-15,"data_quality_pnl":-5}]}
```

The endpoint fails closed unless components reconcile to reported P&L (within one cent). This is attribution, not a causal claim.
