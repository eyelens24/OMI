# Quant Doctor replay bundle and data contract

Every production diagnosis must be tied to an immutable replay bundle. A graph without this evidence is only a dashboard hypothesis.

## Required replay-bundle identity

```text
run_id
strategy name and code hash
container/runtime image hash
parameter set and random seed
model/feature versions
instrument universe and timezone
market-data vendor, snapshot ID, and adjustment version
start/end timestamps
```

## Time-aligned event streams

| Stream | Minimum fields |
|---|---|
| Market | timestamp, symbol, trade/quote, bid, ask, volume, depth, volatility |
| Features | timestamp, symbol, feature values, signal, model confidence |
| Strategy decisions | timestamp, intended target/quantity, reason/signal, decision latency |
| Orders/fills | order ID, submission/ack/fill timestamps, price, quantity, status, commission |
| Portfolio | positions, cash, gross/net exposure, factor exposure, risk limits |
| External events | event timestamp, source, entity, topic, surprise/sentiment where available |
| Operations | deployment hash, errors, restarts, API health, clock skew |

## Fundamental-thesis fields

For the Fundamental Quant Doctor route, supply a `timestamp`, `symbol` where
available, numeric `return`, and numeric strategy `pnl`. Add at least two of
the following point-in-time (as-of) fundamental fields:

| Thesis area | Supported fields | Direction the audit treats as adverse |
| --- | --- | --- |
| Earnings / growth | `revenue_growth_yoy`, `eps_growth_yoy`, `earnings_surprise_pct`, `free_cash_flow_yield` | Lower |
| Forward estimates | `earnings_revision_pct`, `analyst_target_upside` | Lower |
| Valuation | `valuation_percentile`, `pe_ratio`, `ev_to_ebitda`, `free_cash_flow_yield` | Higher multiple/percentile, lower yield |
| Balance sheet | `debt_to_ebitda`, `interest_coverage` | Higher debt, lower coverage |

Fundamentals must be the values available at that timestamp—not values revised
later. The app detects changed patterns and relationships; it cannot prove that
the fundamentals caused a return, or that a valuation level is universally bad.

## Fundamental-alpha decision trail

To distinguish a thesis failure from an alpha, portfolio, or data problem, add
the strategy artefacts that were available at each decision time:

| Layer | Useful fields | What the app checks |
| --- | --- | --- |
| Research signal | `alpha_score`, `expected_return`, `information_coefficient`, `rank_ic`, `hit_rate` | Whether the signal’s recent predictive quality weakened |
| Portfolio translation | `weight_error_bps`, `target_actual_weight_gap_bps`, `factor_exposure_error` | Whether the intended portfolio became the realised portfolio |
| Point-in-time lineage | `fundamental_age_days`, `as_of_lag_days`, `revision_lag_days`, `restatement_gap_pct` | Whether inputs were stale, delayed, or revised after the decision |

These fields should be captured from the original research and order pipeline,
not reconstructed after a loss. The confirmation plan tells the user which
replay or control could reject the leading hypothesis.

## Outcome decomposition

The app should store these separately for each bar and aggregate them by incident:

```text
expected_pnl              # strategy expectation before live frictions
realised_pnl / pnl        # actual broker outcome
implementation_shortfall  # expected_pnl − realised_pnl
fees
slippage_bps
gross_signal_pnl
```

This distinguishes strategy/regime failure from execution failure.

## Storage and retention

- Store raw data snapshots immutably; never overwrite a replay input.
- Store diagnosis outputs with the algorithm version and reviewer status.
- Reconcile intended orders, broker acknowledgements, and fills by order ID.
- Treat credentials as external configuration, never bundle them into a replay artifact.
