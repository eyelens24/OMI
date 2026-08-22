# Incident-label taxonomy

These are **hypothesis labels**, not automatically proven causes. A label may
be emitted only when the required evidence exists; an unfamiliar pattern must
remain `unknown_or_insufficient_evidence` for human review.

| Group | Labels | Evidence needed |
| --- | --- | --- |
| Earnings and growth | `earnings_estimate_cut`, `negative_earnings_surprise`, `revenue_growth_slowdown`, `eps_growth_slowdown`, `margin_compression`, `guidance_cut`, `cash_flow_deterioration`, `working_capital_stress` | Point-in-time filings; estimates/surprises require an estimate vendor. |
| Valuation and balance sheet | `valuation_derating`, `valuation_stretch`, `debt_leverage_increase`, `interest_coverage_deterioration`, `liquidity_runway_risk`, `dilution_risk`, `dividend_or_buyback_cut` | Point-in-time filings, price, shares outstanding. |
| Alpha research | `alpha_score_decay`, `alpha_rank_decay`, `information_coefficient_decay`, `rank_ic_decay`, `hit_rate_decay`, `feature_distribution_shift`, `factor_exposure_drift`, `model_version_change` | Private score/rank, realised forward returns, feature and version snapshots. |
| Portfolio construction | `target_actual_weight_gap`, `concentration_breach`, `leverage_breach`, `sector_exposure_drift`, `country_exposure_drift`, `beta_exposure_drift`, `turnover_spike`, `rebalance_failure` | Private targets, realised positions, risk and constraint snapshots. |
| Execution | `spread_widening`, `slippage_spike`, `fill_rate_drop`, `order_reject_spike`, `latency_spike`, `fee_spike`, `partial_fill_risk`, `broker_reconciliation_break` | Orders, fills, quotes, fees, and broker records. |
| Data lineage | `fundamental_data_stale`, `as_of_lag_increase`, `revision_delivery_lag`, `missing_data_spike`, `vendor_disagreement`, `timestamp_misalignment`, `corporate_action_mismatch`, `look_ahead_risk` | Vendor timestamps, source revisions, quality checks, and point-in-time snapshots. |
| Operations | `strategy_version_change`, `parameter_change`, `deployment_failure`, `api_disconnect`, `api_error_spike`, `restart_loop`, `clock_skew`, `configuration_drift` | Deployment, configuration, and runtime logs. |
| Market/context | `market_volatility_shock`, `liquidity_contraction`, `sector_drawdown`, `factor_rotation`, `macro_rate_shock`, `currency_shock`, `event_risk`, `crowding_unwind` | Market, factor, sector, macro, and event data. |
| Outcome and uncertainty | `stock_specific_drawdown`, `strategy_loss`, `persistent_prior_issue`, `multiple_plausible_causes`, `unknown_or_insufficient_evidence` | P&L plus the relevant upstream evidence. |

## What SEC public data can and cannot label

The SEC importer can support reported-fundamental labels such as growth,
earnings, cash-flow, leverage, and interest coverage. It cannot recover the
strategy’s decision, consensus estimates, trade execution, or the exact time a
filing became usable. Those labels remain unavailable until decision logs and
licensed/vendor data are supplied.

## Labelling protocol for model training

1. Store one incident window per symbol and decision timestamp.
2. Let the rules engine propose up to three labels with evidence links.
3. Require a quant reviewer to select, reject, or add `unknown`.
4. Keep the reviewer decision, strategy ID, model version, and evidence hash.
5. Split train/validation/test sets by time and strategy; never randomly mix
   future incidents into the training set.
6. Measure precision, recall, calibration, and abstention quality per label.

This creates data suitable for training a classifier or ranking model later;
it is not a claim that public market data proves causation.
