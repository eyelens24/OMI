# How Quant Doctor makes a diagnosis

Quant Doctor does not use an LLM to invent causes. Its current decisions are made by small, inspectable statistical algorithms.

## 1. Find usable inputs

The CSV must contain `timestamp` and `pnl`. Every additional numeric column is included as a candidate signal. Constant or non-numeric columns are ignored.

## 2. Detect unusual behaviour

- A **z-score** compares recent values with the early baseline.
- A **change-point scan** finds the time where neighbouring rolling averages differ most.
- The result flags *what changed* and *when*, before attempting explanation.

## 3. Infer an upstream regime hypothesis

When at least two of these features are available—volatility, spread, slippage, news risk, and volume ratio—the app standardises them and builds a market-stress score:

```text
stress score = average(
  volatility z-score,
  spread z-score,
  slippage z-score,
  news-risk z-score,
  −volume-ratio z-score
)
```

It then runs deterministic two-cluster **k-means** over that score. The cluster with the higher average score is labelled `Market stress regime`; the other is normal.

This gives a useful, explainable *upstream hypothesis*. It is not independent causal proof, because the regime is constructed from the same observed features it explains.

## 4. Test each candidate relationship

For each permitted source → target pair, the app calculates:

- **Pearson correlation:** linear co-movement.
- **Spearman correlation:** rank/monotonic co-movement.
- **Lagged correlation:** whether a source change tends to appear before the target change at 0–36 five-minute intervals.
- **Partial correlation:** relationship remaining after controlling for one alternate variable.
- **Approximate p-value:** likelihood of observing the relationship under a zero-correlation assumption.

The current score is:

```text
relationship score
  = |partial correlation|
  × |best lagged correlation|
  × confidence
```

It ranks hypotheses; it does not prove causation.

## 5. Build an understandable path

The whiteboard applies domain constraints so it does not show every mathematically possible arrow as a cause:

```text
Market stress regime / news
  → volatility and liquidity
  → spread and signal quality
  → slippage
  → strategy loss
```

The app retains the best root-to-mechanism paths, mechanism-to-contributor paths, and contributor-to-P&L paths. Each arrow receives a plain-language explanation template and still exposes the underlying numbers on click.

## 6. What this algorithm cannot decide

- A high correlation cannot identify the real-world event that caused a regime change.
- It can miss omitted variables that were not uploaded.
- Testing many relationships increases false-positive risk; production needs multiple-testing correction.
- Arbitrary direction should not be inferred merely because one time series leads another.
- The current two-state regime model is deliberately simple. A production version should evaluate HMMs, change-point models, labelled events, and domain constraints.

The correct user-facing language is therefore **likely upstream hypothesis**, **possible mechanism**, and **evidence path**—never “proven root cause.”
