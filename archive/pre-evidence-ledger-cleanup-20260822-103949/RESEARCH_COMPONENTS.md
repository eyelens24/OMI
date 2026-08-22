# Quant Doctor research map

This document is the component map for a system that diagnoses why a quantitative strategy's P&L changed. It treats every explanation as a **testable hypothesis**, not a fact.

## The outcome to explain

At the highest level, realised P&L can be decomposed as:

```text
Realised P&L
  = expected signal return
  − execution costs
  − financing / fees
  ± portfolio and market exposure effects
  ± data / operational errors
```

The root diagnosis question is therefore not simply “why did P&L fall?” but:

> Which conditions changed, which parts of the trading process did they affect, and is the observed P&L deterioration still present after controlling for alternative explanations?

## Root topic map

The active prototype scope is deliberately **non-fundamental**. It does not try to infer a company’s intrinsic value or use news sentiment as a root cause. Market volatility and liquidity remain context because they affect execution and a model's realised performance.

```text
Market context ─┬─> Signal / model health ───────┐
                ├─> Liquidity / execution ───────┼─> Realised P&L
Portfolio/risk ─┼─> Exposure / sizing ───────────┤
Data quality ───┼─> Strategy decisions / fills ──┤
Operations ─────┴─> Latency, outages, reconciliation
```

## Root-hypothesis layer

Quant Doctor should distinguish three levels: a **latent upstream regime**, observed **mechanisms**, and the **P&L outcome**. The current prototype uses deterministic two-cluster k-means over aligned volatility, news-risk, and inverse-liquidity features to infer a normal-versus-stressed regime. It deliberately excludes spread and slippage from this label, so an explanation such as `market stress → wider spreads → slippage` is not circular. It then adds `Market stress regime` as an upstream hypothesis in the evidence graph.

This is deliberately explainable unsupervised ML, not a black-box causal claim. The system must display the features that defined the cluster, its separation confidence, and the paths from the inferred regime into observed mechanisms. In a production system, compare this approach with Hidden Markov Models, Bayesian change-point models, and supervised labels from known market events.

## 1. Market regime

**Question:** Did the market enter conditions where this strategy historically behaves differently?

| Measure | Why it matters | Example test |
|---|---|---|
| Realised/implied volatility | Many signals and costs change with volatility | Compare P&L conditional on volatility regime |
| Trend strength / momentum | Mean reversion can fail in persistent trends | Test signal hit rate by trend bucket |
| Volume, depth, spread | Determines tradability and market impact | Test lagged liquidity → slippage relationship |
| Cross-asset correlation | Diversification can vanish in shocks | Compare portfolio correlation before/after change point |
| Rates, index, sector returns | Reveals common-factor exposure | Regress residual P&L on factors |

**Research methods:** regime clustering, Hidden Markov Models, rolling volatility, change-point detection, conditional distributions.

## 2. Signal / alpha deterioration

**Question:** Did the strategy's prediction or edge stop working before execution costs?

| Measure | Why it matters |
|---|---|
| Signal strength and frequency | Detects weaker or rarer opportunities |
| Hit rate / win rate | Checks directional accuracy |
| Expected value per trade | Separates fewer wins from worse payoff |
| Signal decay / holding period | Checks whether the intended horizon changed |
| Feature distributions / model residuals | Detects model or feature drift |
| Model confidence / calibration | Finds overconfident predictions |

**Key tests:** forward-return by signal bucket, calibration curves, population stability index, KS test, residual autocorrelation, P&L before estimated costs.

## 3. Execution and liquidity

**Question:** Was the alpha present but consumed by worse execution?

| Measure | Why it matters |
|---|---|
| Quoted and realised spread | Measures crossing and adverse selection |
| Slippage | Direct difference between expected and fill price |
| Fill rate / partial fills / rejects | Detects incomplete execution |
| Latency | Can turn valid signals stale |
| Order size ÷ market volume | Proxy for market impact |
| Commissions and fees | Direct P&L drag |

**Key tests:** arrival-price implementation shortfall, spread → slippage lagged correlation, regression of slippage on volatility/depth/order size, realised-versus-simulated P&L decomposition.

## 4. Portfolio construction and risk

**Question:** Did normal losses become dangerous because of exposure, concentration, or correlation?

| Measure | Why it matters |
|---|---|
| Gross/net leverage | Loss amplification |
| Position size and concentration | Single-name/sector dependency |
| Factor and beta exposure | Hidden directional bets |
| Strategy correlation | Multiple strategies may be the same trade |
| Drawdown, VaR, expected shortfall | Tail-risk severity |
| Turnover and capacity | Cost and impact sensitivity |

**Key tests:** factor regression, contribution-to-risk, conditional correlation, stress tests, drawdown attribution, concentration limits.

## 5. News and exogenous events

**Question:** Did a time-stamped event plausibly precede a market or execution change?

| Input | Examples |
|---|---|
| Structured economic calendar | CPI, rates, payrolls, central-bank decisions |
| Company/sector news | Earnings, guidance, halts, M&A |
| Market news | Geopolitical shocks, index rebalances, exchange events |
| Event labels | Topic, entity, sentiment, surprise, timestamp |

**Key tests:** event study windows, abnormal return/volume/spread around events, event → volatility lag, compare affected instruments with controls. News is supporting evidence; text sentiment alone must never be treated as proof of cause.

## 6. Data quality

**Question:** Did the strategy act on stale, incorrect, incomplete, or differently adjusted data?

| Check | Examples |
|---|---|
| Freshness | Last received tick, feature timestamp, clock skew |
| Completeness | Missing bars, null values, missing universe members |
| Integrity | Duplicate ticks, outliers, crossed markets, bad corporate-action adjustments |
| Consistency | Different vendor values, timezone mismatch, symbol mapping errors |
| Feature pipeline | Schema changes, failed joins, stale model inputs |

**Key tests:** data-quality assertions, vendor reconciliation, missingness analysis, raw-versus-derived feature comparison, timestamp lineage.

## 7. Operational and system causes

**Question:** Did software, broker, or infrastructure behaviour differ from the intended strategy?

| Measure | Examples |
|---|---|
| Strategy version and parameter hash | Wrong code/configuration deployed |
| Decision logs | Signal generated but no order submitted |
| Broker acknowledgements | Rejected, delayed, or duplicate orders |
| Broker/local reconciliation | Positions and fills disagree |
| Network/API health | Disconnects, rate limits, stale sessions |
| Runtime metrics | CPU, memory, errors, restarts |

**Key tests:** replay exact deployment bundle, compare intended/placed/acknowledged/filled orders, audit event timeline, reconciliation checks.

## Evidence needed for each graph edge

Every arrow on the whiteboard should record:

```text
source topic → target topic
time window and instrument universe
Pearson and Spearman correlation
best time lag and lagged correlation
partial correlation after stated controls
regression coefficient / uncertainty
p-value and multiple-testing adjustment
sample size and regime consistency
data provenance and transformation version
human reviewer status: unreviewed / accepted / rejected
```

## Recommended research/build order

1. Preserve replay bundles: code hash, parameters, data snapshot, model weights, fills, runtime version.
2. Build P&L decomposition: signal return, execution cost, fees, exposure.
3. Add data-quality and reconciliation checks; these prevent misleading mathematics.
4. Implement robust regime/change-point detection.
5. Add conditional/partial relationships and multiple-testing correction.
6. Add news/event studies with aligned timestamps.
7. Add continuous ingestion, alerts, and human investigation history.

## Important limitations

- Correlation, regression, and time ordering do not prove causation.
- Many simultaneous tests create false positives; adjust for multiple comparisons and show uncertainty.
- Reproduction only works when the full data, configuration, code version, model state, and execution conditions were retained.
- A strategy can lose for several valid reasons at once. The product should rank and expose competing explanations, not manufacture one definitive story.
