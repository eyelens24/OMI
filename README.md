# OMI — Decision-to-P&L Incident Forensics

OMI is a **local, read-only forensic prototype** for systematic-investment and AI-assisted decision incidents.

It is not a trading bot, broker terminal, order-management system, stock picker, or automatic execution tool.

Its core question is deliberately narrow:

> **At the time of a loss, what did the system know, what did it decide, what did it intend to own, what actually happened, and which evidence proves or breaks each link to P&L?**

The product principle is:

```text
No evidence, no story.
```

A fluent narrative is not a diagnosis. OMI must show the underlying evidence route, mark missing/contradictory links, and let another investigator reproduce the result.

## Repository layout

The project is organized by concern so the code, data, and historical archives are easy to navigate:

- `omi_core/` — core Python logic for evidence, attribution, and investigation graphs.
- `tests/` — regression and behavior tests for the forensic pipeline.
- `sample_data/` — bundled CSV fixtures and synthetic data generators.
- `e2e/` — browser-based Playwright end-to-end checks.
- `examples/` — example payloads and demonstration artifacts.
- `archive/` — historical or superseded experiment notes and deployment artifacts.
- top-level Python scripts — entry points and utilities for running the app and model workflow.

---

## Local-only safety boundary

OMI is intentionally:

```text
local-only
read-only
receipt-driven
no order routing
no broker/account mutation
no execution of uploaded strategy code
```

The app binds to `127.0.0.1` and has no live-trading controls.

---

## Start OMI on Windows

```powershell
cd C:\Users\User\OMI
powershell -ExecutionPolicy Bypass -File .\Start-OMI.ps1
```

Open:

```text
http://127.0.0.1:8000
```

The native runtime is:

```text
C:\conda2\python.exe
```

---

## Demo workflow

1. Open OMI and click **Run built-in test CSV**.
2. Inspect the incident timeline and select a material loss.
3. Read the **Explanation built from your data** flow:
   ```text
   observed break → decision/translation mechanism → outcome
   ```
4. Use the replay control in that same section. It rebuilds the investigation using only records available by the selected point in time.
5. Check the displayed immutable **snapshot ID**.
6. Select a different loss, then reselect the first loss. The snapshot and explanation must return to the same values.
7. Export a reproducibility receipt when available.

The bundled demo is synthetic. It demonstrates deterministic mechanics and known-truth regression scenarios; it does not establish real broker, vendor, or market truth.

---

# Product architecture

## 1. The Evidence Ledger

OMI is being rebuilt around a typed decision-to-P&L evidence ledger. Every incident should be expressible as this chain:

```text
observation
→ decision
→ target
→ fill
→ position
→ P&L
```

### Evidence status taxonomy

Every ledger step and link receives one status:

| Status | Meaning |
| --- | --- |
| `supported` | Supplied records link correctly and are time-valid. |
| `missing` | Required record or linkage was not supplied. |
| `contradicted` | Supplied records disagree, such as a parent ID that cannot be found. |
| `time-invalid` | A record was only available after the decision it supposedly informed; this is lookahead. |
| `inferred` | A bounded hypothesis generated from evidence patterns; never a proven cause. |

A conclusion can be strong only where the relevant chain is supported. Missing data must be represented as an evidence gap, not silently filled with model prose.

### Immutable investigation snapshots

A snapshot identity is derived deterministically from:

```text
as-of timestamp
+ source identifier
+ exact retained evidence rows
```

Every visible surface must use the same snapshot:

```text
headline metrics
explanation cards
ledger links
replay time
reconciliation status
exported receipt
```

This prevents a UI from mixing an old explanation with newer P&L or a different evidence window.

### Point-in-time rule

A record may only support a decision if it was available on or before the decision timestamp:

```text
available_at <= decision_timestamp
```

`observed_at` alone is insufficient. Fundamentals, research data, market data, and AI outputs may be revised later; OMI needs the actual version that was available at decision time.

---

## 2. What OMI should diagnose

OMI should automatically construct a replayable investigation route for every incident, without a human drawing arrows.

### Evidence-complete route

When all records are present and reconcile:

```text
Vendor snapshot V-18 available at 09:25
→ model run M-492 decided at 09:30
→ target T-77 at 09:31
→ fill F-882 at 09:32
→ position P-19
→ P&L at 16:00
```

The app should report the exact supported mismatch or contributor:

```text
Target was 5.0%; fills reached 3.8%.
The decision-to-target link is supported.
The target-to-fill discrepancy is supported.
The P&L chain reconciles.
Therefore execution/translation is supported as a contributor.
```

### Evidence-gap route

When the chain is incomplete, OMI must still render a useful investigation path:

```text
Observed P&L loss
→ candidate layer: data / decision / target translation / execution / market
→ missing evidence required to confirm or reject that route
→ bounded conclusion: hypothesis, not established cause
```

It must not show a blank panel and it must not call a generated route causal proof.

---

## 3. AI decision failure forensics

For an AI or ML-driven strategy, "why did it decide that?" requires more than a final score. OMI must retain the **decision provenance**.

### Required AI/strategy decision record

| Field | Why it matters |
| --- | --- |
| `decision_id` | Stable identifier connecting decision to target/order chain. |
| `strategy_id`, `strategy_version` | Identifies the deployed logic. |
| `model_id`, `model_version`, `model_hash` | Identifies the exact AI/model artifact. |
| `run_id`, `prompt_or_policy_version` | Makes a specific inference run reproducible. |
| `parameter_hash` | Captures optimizer/policy configuration. |
| `decision_timestamp` | The time the strategy acted. |
| `available_at` | Proves the data/model output was available then. |
| `symbol` / portfolio entity | Joins the decision to target, fills, and P&L. |
| `action`, `target_weight`, `target_quantity` | States intended action, not merely a narrative. |
| `score`, `rank`, `expected_return`, `confidence` | Captures the model’s expressed belief. |
| `feature_snapshot_id` / input hashes | Identifies exactly what the model saw. |
| `reason_codes` / feature contributions | Human-readable, structured rationale—not free-form post-hoc prose. |
| `raw_artifact_hash` | Allows evidence integrity checks. |

### AI failure classes OMI should distinguish

| Failure class | Evidence needed | Example conclusion |
| --- | --- | --- |
| Input/data failure | point-in-time vendor snapshots, availability times, revisions, feature hashes | “The model used a stale/revised input.” |
| Model/policy failure | model version, features, score/rank, policy/prompt, decision record | “The deployed model ranked this asset despite adverse supported inputs.” |
| Portfolio translation failure | decision, target, optimizer constraints, target output | “The decision did not translate to the intended target.” |
| Execution failure | order/fill IDs, timestamps, price, fees, venue, slippage | “The target was correct; execution diverged materially.” |
| Position/accounting failure | fill-position mapping, corporate actions, valuation marks | “The reported P&L does not reconcile to the held position.” |
| Market/regime failure | benchmark/factor/exposure/market records available at time | “Market movement explains observed loss; no data fault is supported.” |
| Explanation failure | model rationale versus actual inputs/policy/result | “The claimed AI rationale contradicts retained decision evidence.” |

OMI should be able to say **where the AI failed** only when this evidence exists. If a model has no retained decision provenance, OMI may say:

```text
The system produced a position, but the supplied records cannot establish why.
Missing: model version, input snapshot, score/rank, policy/prompt, and decision artifact.
```

That is a useful finding, not a failure of the product.

---

# Data to research, acquire, and retain

## Strategy and AI sources

Research where the deployment currently records:

- strategy/model registry and immutable model artifacts;
- experiment tracking and evaluation results;
- model/prompt/policy versions;
- feature store snapshots and feature definitions;
- decision logs, score/rank outputs, rationale/reason codes;
- optimizer inputs, constraints, and target output;
- source-control commit and dependency lockfile hashes.

Questions to answer:

1. Can we retrieve the exact model/policy version that made a decision?
2. Can we reconstruct its exact input data and feature values as available then?
3. Are scores, ranks, confidence, action, and target output retained?
4. Are reasons structured evidence, or merely generated natural language?
5. Can a model’s rationale be tested against its actual retained inputs?

## Market and fundamental data sources

For every source, research:

- point-in-time historical availability, not merely observation date;
- revision/version history;
- stable symbol/entity mapping;
- corporate action, split, dividend, delisting, and currency treatment;
- vendor licensing and retention rights;
- raw file/API artifact hashes and ingestion timestamp.

Minimum fields:

```text
source
vendor/version
symbol/entity mapping
observed_at
available_at
retrieved_at
snapshot/version ID
raw artifact hash
metric values
revision lineage
```

## Broker, OMS, and accounting sources

Required records:

```text
order_id
fill_id
parent target/decision IDs
side
quantity
price
fees
venue
order/fill timestamps
position quantity
valuation/mark timestamp
realized and unrealized P&L
corporate action adjustments
```

Research questions:

1. Are order/fill identifiers stable enough to join exactly?
2. Can order lifecycle and amendments/cancellations be exported?
3. Does P&L reconcile to positions after fees, FX, dividends, and corporate actions?
4. Is the supplied P&L realized, unrealized, gross, net, or benchmark-relative?

---

# Current implementation status

Implemented and tested:

- local-only native Windows startup;
- incident CSV and Incident Bundle validation paths;
- immutable snapshot IDs;
- no-lookahead replay;
- selected-loss race protection;
- reproducibility receipts and local Incident Command endpoint;
- additive attribution validation;
- automatic evidence-flow fallback with `supported`, `candidate`, and `gap` labels;
- typed Evidence Ledger foundation for:
  ```text
  observation → decision → target → fill → position → P&L
  ```
- browser checks for demo load, console errors, and A → B → A selected-loss determinism.

In progress for the proper rebuild:

- wire typed ledger records through every import/replay route;
- render ledger links, evidence status, and raw receipts in the primary card flow;
- generate known-truth synthetic AI failure scenarios;
- test supported, missing, contradictory, and time-invalid routes in browser and API suites;
- add contradiction reports between model rationale and retained model inputs.

---

# Verification

Run Python/API tests:

```powershell
C:\conda2\python.exe -m unittest discover -s tests -q
```

Check frontend syntax:

```powershell
node --check .\app.js
```

Run browser tests:

```powershell
npx playwright test
```

A release claim requires all of these to pass, plus a local health check:

```powershell
Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8000/healthz
```

---

# Accuracy boundary

OMI can make deterministic, reproducible claims about the records supplied to it:

- whether a link exists;
- whether it is time-valid;
- whether quantities/P&L reconcile;
- which model/data/decision artifact was supplied;
- what evidence is missing or contradictory.

OMI cannot establish real-world causal truth from synthetic data, missing provenance, or correlation alone.

```text
Complete record chain + reconciliation
≠ universal proof of economic causality

Missing record chain
≠ permission to invent a causal narrative
```

That restraint is the point. OMI is not meant to make losses sound explained; it is meant to make the evidence trail impossible to bluff.
