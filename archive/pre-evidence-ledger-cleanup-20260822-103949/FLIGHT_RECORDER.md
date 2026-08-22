# Local Flight Recorder

The flight recorder is a local, read-only event collector. It never submits,
changes, or cancels orders. A strategy, broker adapter, or small sidecar process
posts facts that have already occurred to `http://127.0.0.1:8000`.

## Event API

Send one strategy's events to:

```text
POST /api/flight-recorder/events
```

Each event needs:

| Field | Meaning |
| --- | --- |
| `strategy_id` | Stable identifier, for example `fundamental_value_v12` |
| `event_type` | One of `fundamental_snapshot`, `strategy_decision`, `portfolio_target`, `order`, `fill`, `position_snapshot`, `pnl_mark`, `heartbeat`, or `data_status` |
| `timestamp` | ISO-8601 time when the event was known or occurred |
| `symbol` | Optional instrument identifier; required for instrument-level diagnosis |
| `data` | JSON object containing event-specific fields |
| `event_id` | Optional stable unique ID. If omitted, the collector hashes the event contents and ignores exact duplicates. |

Example: record the information available when the model makes a decision.

```json
{
  "events": [
    {
      "strategy_id": "fundamental_value_v12",
      "event_type": "fundamental_snapshot",
      "timestamp": "2026-08-21T09:30:00Z",
      "symbol": "AAPL",
      "data": {
        "earnings_revision_pct": -4.2,
        "revenue_growth_yoy": 3.1,
        "valuation_percentile": 0.86,
        "fundamental_age_days": 1.2,
        "as_of_lag_days": 0.4
      }
    },
    {
      "strategy_id": "fundamental_value_v12",
      "event_type": "strategy_decision",
      "timestamp": "2026-08-21T09:30:00Z",
      "symbol": "AAPL",
      "data": {
        "alpha_score": 0.82,
        "expected_return": 2.1,
        "rank_ic": 0.06,
        "model_version": "v12.4",
        "parameter_hash": "e4c19"
      }
    },
    {
      "strategy_id": "fundamental_value_v12",
      "event_type": "portfolio_target",
      "timestamp": "2026-08-21T09:30:00Z",
      "symbol": "AAPL",
      "data": {
        "target_weight": 0.018,
        "weight_error_bps": 0
      }
    },
    {
      "strategy_id": "fundamental_value_v12",
      "event_type": "pnl_mark",
      "timestamp": "2026-08-21T16:00:00Z",
      "symbol": "AAPL",
      "data": {
        "return": -0.012,
        "pnl": -420.50,
        "equity": 999579.50
      }
    }
  ]
}
```

The collector appends the events into local SQLite storage. It never overwrites
an event. Events with the same `event_id`, or identical events without an ID,
are ignored as duplicates.

## Diagnose a recorded incident

```text
POST /api/flight-recorder/analyse
```

```json
{
  "strategy_id": "fundamental_value_v12",
  "start": "2026-08-01T00:00:00Z",
  "end": "2026-08-31T23:59:59Z"
}
```

The current analysis needs at least 50 P&L marks. For every P&L mark, it uses
the latest prior-or-equal evidence for that `symbol`; it never uses a later
fundamental snapshot or model decision as input to an earlier outcome.

## Collector status

```text
GET /api/flight-recorder/status?strategy_id=fundamental_value_v12
```

This returns event count, latest recorded timestamp, and counts by event type.

## Important limits

- This first collector does not connect to IBKR or any other broker.
- It does not run in a background process by itself; the strategy or a separate
  adapter must post events as they occur.
- It does not execute trading actions or hold broker credentials.
- Exact replay still requires the firm to retain its model code/configuration,
  point-in-time vendor snapshots, corporate actions, and actual order/fill data.
