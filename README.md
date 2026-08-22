# Doctor Quant â€” Decision-to-P&L Incident Forensics

Doctor Quant is a **local, read-only forensic prototype** for systematic-investment and AI-assisted decision incidents.

It is not a trading bot, broker terminal, order-management system, stock picker, or automatic execution tool.

Its core question is deliberately narrow:

> **At any point in a position's history, what did the system know, what did it decide, what did it intend to own, what actually happened, and which evidence proves or breaks each link to P&L?**

In the product, that becomes a single **Decision Receipt** for a selected trade:

```text
position before â†’ BUY, SELL, or HOLD â†’ why â†’ inputs available beforehand
â†’ intended size â†’ actual execution â†’ position after â†’ P&L â†’ trust status
```

The receipt is deliberately concise. Doctor Quant does not generate an after-the-fact story; it displays the rationale and signals retained when the decision was made, then labels whether the supporting chain is complete, missing, contradictory, or time-invalid.

The product principle is:

```text
No evidence, no story.
```

A fluent narrative is not a diagnosis. Doctor Quant must show the underlying evidence route, mark missing/contradictory links, and let another investigator reproduce the result.

## Repository layout

The project is organized by concern so the code, data, and historical archives are easy to navigate:

- `doctorquant_core/` â€” core Python logic for evidence, attribution, and investigation graphs.
- `tests/` â€” regression and behavior tests for the forensic pipeline.
- `sample_data/full_product_demo.csv` â€” the single bundled presentation CSV and its generator.
- `e2e/` â€” browser-based Playwright end-to-end checks.
- `examples/` â€” example payloads and demonstration artifacts.
- `requirements.txt` â€” Python runtime dependency manifest; currently standard-library only.
- `archive/` â€” historical or superseded experiment notes and deployment artifacts.
- top-level Python scripts â€” entry points and utilities for running the app and model workflow.

---

## Local-only safety boundary

Doctor Quant is intentionally:

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

## Install and start Doctor Quant

### Requirements

- Python 3.10 or newer.
- A current web browser.
- `requirements.txt` is the Python dependency manifest. It is intentionally empty of packages because the current application uses only the Python standard library.
- Node.js is optional and is needed only for frontend and Playwright verification.

Confirm that Python is available:

```text
Windows:  py -3 --version
macOS:    python3 --version
```

If the command is missing or reports a version older than 3.10, install a current Python 3 release before continuing.

### Windows

1. Download or clone Doctor Quant and open PowerShell in the Doctor Quant folder.
2. Create an isolated Python environment and install the declared requirements:

   ```powershell
   py -3 -m venv .venv
   .\.venv\Scripts\Activate.ps1
   python -m pip install -r requirements.txt
   ```

   The install currently downloads nothing because Doctor Quant has no third-party runtime packages. Keeping this step makes future dependency updates automatic.
3. Start the application:

   ```powershell
   python .\run-doctorquant.py
   ```

   If PowerShell blocks environment activation, use `.\.venv\Scripts\python.exe .\run-doctorquant.py` directly.
4. Open [http://127.0.0.1:8000](http://127.0.0.1:8000) in a browser.
5. Leave PowerShell open while using Doctor Quant. Press `Ctrl+C` there to stop it.

You can alternatively double-click `Start-DoctorQuant-Server.cmd`; it tries the included Conda path first and then the normal Windows Python launchers.

Check the local server:

```powershell
Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8000/healthz
```

### macOS

1. Download or clone Doctor Quant and open Terminal in the Doctor Quant folder.
2. Create an isolated Python environment and install the declared requirements:

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   python -m pip install -r requirements.txt
   ```

   The install currently downloads nothing because Doctor Quant has no third-party runtime packages.
3. Start the application:

   ```bash
   python run-doctorquant.py
   ```

   Or use the included launcher:

   ```bash
   chmod +x start-doctorquant.sh Start-DoctorQuant.command
   ./start-doctorquant.sh
   ```

   After it has execute permission, `Start-DoctorQuant.command` can also be opened from Finder.
4. Open [http://127.0.0.1:8000](http://127.0.0.1:8000) in a browser.
5. Leave Terminal open while using Doctor Quant. Press `Control+C` to stop it.

Check the local server:

```bash
curl http://127.0.0.1:8000/healthz
```

### Use another port

If port `8000` is already occupied, choose another local port:

```powershell
# Windows PowerShell
$env:PORT = "8001"
python .\run-doctorquant.py
```

```bash
# macOS
PORT=8001 python run-doctorquant.py
```

Then open `http://127.0.0.1:8001`. Recorder examples must use the same port in their `--server` URL.

---

## How to use Doctor Quant

### 1. Explore the complete built-in example

1. Start Doctor Quant and open the local dashboard.
2. Click **Run complete CSV demo**.
3. Select AAPL, MSFT, NVDA, JPM, or XOM above the position chart.
4. Click any point. The line shows shares held and the coloured dots show BUY, SELL, and HOLD decisions.
5. Read the **Algorithm Action Receipt** for the latest decision, saved reason, intended size, fill, resulting position, and P&L.
6. Expand **What the algorithm knew** to inspect the inputs available before that decision.
7. Open **Show verification details** to inspect the linked evidence chain.
8. Click **Export reproducibility receipt** to save the investigation as JSON.

Each demo stock behaves independently: AAPL uses RSI, MSFT uses momentum, NVDA uses a volatility gate, JPM uses bank fundamentals, and XOM uses oil and inventory indicators.

### 2. Analyse your own combined CSV

Click **Upload one incident CSV** and select a local file. Recommended columns are:

| Column | Requirement | Meaning |
| --- | --- | --- |
| `timestamp` | Required | ISO-8601 time for the record. |
| `pnl` | Required for statistical analysis | P&L for the observation. Aliases such as `net_pnl` and `realized_pnl` are normalized. |
| `symbol` | Recommended | Stock or instrument identifier. |
| `action` | Recommended | `BUY`, `SELL`, or `HOLD`. |
| `decision_reason` | Recommended | Explanation retained when the strategy acted. |
| `position_quantity` | Recommended | Actual shares held. |

Additional pre-decision columns can be indicators; Doctor Quant detects their names dynamically. A fully verified receipt also needs the lifecycle and provenance fields described under **Complete-example format** below.

Statistical diagnosis requires at least 50 timestamped rows with numeric P&L. A shorter file can still be useful as typed lifecycle evidence, but it will not produce the full statistical analysis.

### 3. Align market information with strategy results

Use **Upload fundamentals + P&L** when inputs and outcomes are separate:

1. Select the market or fundamental CSV.
2. Select the strategy/P&L CSV.
3. Doctor Quant joins each strategy observation to the newest market record available at or before its timestamp.

Both files need `timestamp`, both should contain `symbol` for symbol-aware alignment, and the strategy file needs `pnl`. Doctor Quant rejects rows that cannot be aligned inside the allowed time gap instead of silently using future information.

### 4. Open a recorded strategy

Keep Doctor Quant running and open a second terminal in the project folder.

Windows:

```powershell
py -3 .\examples\instrumented_strategy.py --server http://127.0.0.1:8000
```

macOS:

```bash
python3 examples/instrumented_strategy.py --server http://127.0.0.1:8000
```

Return to the dashboard and click **Open latest recorded strategy**. Doctor Quant displays the decisions and evidence appended by that strategy. The recorder observes the strategy; it never submits an order.

### 5. Understand incomplete results

- **Supported**: the supplied records form a linked and time-valid step.
- **Missing**: the required event or parent link was not supplied.
- **Contradicted**: retained records disagree.
- **Time-invalid**: evidence became available only after the decision.
- **Inferred**: the result is an investigative hypothesis rather than a retained fact.

Doctor Quant does not manufacture missing actions or explanations. A partial CSV can still be analysed, but the dashboard identifies what it cannot prove.

---

## Connect an unfamiliar trading algorithm

Doctor Quant now includes a framework-neutral Python flight recorder in [`doctorquant_core/recorder.py`](doctorquant_core/recorder.py). Its purpose is:

> Connect an unfamiliar trading algorithm, capture its decision state, and later reproduce why a position changed through one common evidence contractâ€”even when the strategy, model, input names, or broker field names differ.

The recorder observes the algorithm. It never places an order and never needs broker credentials.

### Fastest complete example

1. Start Doctor Quant.
2. In a second terminal, run:

   ```powershell
   py -3 .\examples\instrumented_strategy.py --server http://127.0.0.1:8000
   ```

   On macOS/Linux:

   ```bash
   python3 examples/instrumented_strategy.py --server http://127.0.0.1:8000
   ```

3. In the dashboard, click **Open latest recorded strategy**.
4. Choose the stock and click any point on its position line.
5. Expand **What the algorithm knew**.

The example runs an ordinary RSI/regime strategy for 60 decisions. It records 360 linked events and deliberately includes an unused vendor field. Doctor Quant excludes that unused field because the instrumented strategy never reads it.

### Minimal integration

An existing strategy whose first argument is a mapping can be wrapped without changing its return value:

```python
from doctorquant_core import HttpSink, StrategyRecorder

recorder = StrategyRecorder(
    "production_alpha_v7",
    strategy_version="git:4a91df2",
    model_version="xgboost:2026-08-22",
    parameters={"buy_threshold": 0.65},
    sink=HttpSink("http://127.0.0.1:8000"),
)

@recorder.instrument()
def decide(features):
    score = features["proprietary_alpha"]
    risk = features["risk_regime"]
    if score > 0.65 and risk != "blocked":
        return {
            "action": "BUY",
            "target_quantity": 500,
            "decision_reason": "Alpha passed the threshold and risk allowed entry.",
        }
    return {
        "action": "HOLD",
        "target_quantity": features["current_position"],
        "decision_reason": "No permitted position change.",
    }

result = decide({
    "symbol": "AAPL",
    "timestamp": "2026-08-22T09:30:00Z",
    "available_at": "2026-08-22T09:29:58Z",
    "proprietary_alpha": 0.81,
    "risk_regime": "normal",
    "current_position": 0,
})
```

The result returned to the trading program is unchanged. The wrapper additionally records:

- the feature keys the function actually accessed;
- their point-in-time values and `available_at` timestamp;
- a deterministic feature-snapshot hash;
- strategy parameters and their hash;
- explicit model version, or a derived callable fingerprint when none is supplied;
- source/bytecode fingerprint of the wrapped decision function;
- action, target, reason, confidence, score, reason codes, and any extra JSON result fields supplied by the strategy.

The decision output must contain `action` (`BUY`, `SELL`, or `HOLD`) and should contain a target plus a human-readable `decision_reason`. Arbitrary indicator names are supported; there is no fixed RSI, momentum, fundamental, or model-feature schema.

### Attach execution, position, and P&L

After the strategy acts, append facts returned by the broker, OMS, or accounting system:

```python
receipt = recorder.latest_receipt("AAPL")

receipt.record_fill(
    quantity=500,
    price=229.14,
    timestamp="2026-08-22T09:30:01Z",
    broker_order_id="order-812",
)
receipt.record_position(
    quantity=500,
    timestamp="2026-08-22T09:30:02Z",
    account="paper-1",
)
receipt.record_pnl(
    pnl=-125.40,
    timestamp="2026-08-22T16:00:00Z",
    currency="USD",
)
```

Doctor Quant refuses invalid ordering: a fill requires a recorded target, a position requires its fill, and P&L requires the resulting position. It also rejects an input whose `available_at` is later than the decision timestamp.

### Adapt different broker field names

The execution adapter maps an external payload without putting vendor-specific names into the core:

```python
from doctorquant_core import ExecutionAdapter

broker = ExecutionAdapter(
    timestamp="eventTime",
    fill_quantity="filledQty",
    fill_price="avgPx",
    position_quantity="netPosition",
    pnl="netPL",
)

broker.record_fill(receipt, {
    "eventTime": "2026-08-22T09:30:01Z",
    "filledQty": 500,
    "avgPx": 229.14,
    "brokerOrderId": "order-812",
})
```

Use `input_selector=` when the strategy's input mapping is not its first argument, and `result_adapter=` when its output is not already a mapping containing Doctor Quant's action/target fields. These two boundaries are where framework- or model-specific adapters belong.

### Storage and inspection

Available sinks are:

- `MemorySink` for tests or embedding;
- `JsonlSink(path)` for an append-only local evidence file;
- `HttpSink(url)` for the local Doctor Quant collector;
- `CompositeSink(...)` for more than one destination.

The collector ignores duplicate event IDs and never overwrites an earlier event. Recorded strategies can be queried through:

```text
GET /api/flight-recorder/strategies
GET /api/flight-recorder/evidence?strategy_id=production_alpha_v7
```

### Connect arbitrary APIs and additional data

[`doctorquant_core/connectors.py`](doctorquant_core/connectors.py) defines the common read-only boundary for external information:

```text
HTTP API / vendor SDK / CSV / JSON / JSONL
â†’ source envelope
â†’ field mapping
â†’ availability check
â†’ merged decision snapshot
â†’ StrategyRecorder
â†’ execution adapter
â†’ Doctor Quant dashboard
```

Built-in connector primitives:

| Component | Purpose |
| --- | --- |
| `HttpJsonConnector` | Calls a JSON API using GET only. Authentication headers are used for the request but never placed in evidence. |
| `CallableConnector` | Wraps any existing Python SDK, database client, feature-store client, model registry, or custom loader function. |
| `FileConnector` | Selects the newest time-valid row from CSV, JSON, JSONL, or NDJSON. |
| `FieldMapper` | Maps nested or vendor-specific fields into the names expected by the strategy and applies optional type/unit transformations. |
| `ConnectorHub` | Reads multiple sources, rejects future evidence, detects field collisions, and creates one merged `ConnectedSnapshot`. |
| `ExecutionAdapter` | Maps broker/OMS/accounting responses into fill, position, and P&L records. |

Example using unrelated market and risk APIs:

```python
from doctorquant_core import CallableConnector, ConnectorHub, FieldMapper

market = CallableConnector(
    "market-vendor",
    fetch=market_client.latest,
    version="market-api-v8",
    observed_at_field="observed",
    available_at_field="published",
    mapper=FieldMapper({
        "rsi_14": "indicators.relativeStrength14",
        "sentiment": "indicators.newsSentiment",
    }),
)

risk = CallableConnector(
    "risk-engine",
    fetch=risk_client.snapshot,
    version="risk-policy-v3",
    mapper=FieldMapper({
        "risk_regime": "state.regimeName",
        "capacity_remaining": "state.capacityRemaining",
    }),
)

snapshot = (
    ConnectorHub()
    .add(market)
    .add(risk)
    .snapshot(decision_time="2026-08-22T09:30:00Z", symbol="AAPL")
)

receipt = recorder.capture_connected_decision(decide, snapshot)
```

Every field in the merged snapshot retains:

- source identifier and connector type;
- observed, available, and retrieval timestamps;
- vendor/schema version;
- hash of the raw source response.

Only sources available on or before the decision are accepted. Duplicate output names fail loudly unless the connector is assigned a prefix or the fields are mapped differently.

The complete multi-source example is [`examples/connected_sources_strategy.py`](examples/connected_sources_strategy.py):

```bash
python3 examples/connected_sources_strategy.py --server http://127.0.0.1:8000
```

To support another API, subclass `EvidenceConnector` and implement its single `read(...) -> SourceEnvelope` method, or wrap the provider's existing client with `CallableConnector`. No change to the ledger, dashboard, or recorder is required.

### What â€œautomaticâ€ does and does not mean

For a mapping-based Python function, Doctor Quant can automatically observe which keys are read and capture its returned decision. The connector layer can normalize any source that exposes a readable payload, but each new provider still needs credentials, a fetch function or URL, timestamp semantics, and a field map. Doctor Quant cannot inspect arbitrary native code, remote model servers, a pandas pipeline, or a broker account without an adapter at that boundary. It also cannot prove that a provider timestamp is truthful or that a human-written reason is economically correct merely because it was recorded.

Production-grade reconstruction still requires the real system to provide its timestamps, immutable model artifacts, data versions, order/fill events, positions, corporate actions, fees, FX treatment, and accounting marks. The recorder makes these facts comparable and replayable; it does not manufacture facts that the connected systems never expose.

## Presentation-ready demo

For the clearest product walkthrough, click **Run complete CSV demo**. It loads [`sample_data/full_product_demo.csv`](sample_data/full_product_demo.csv), the one bundled CSV. It contains five independent strategies with changing share positions, BUY/SELL/HOLD actions, saved reasons, strategy-specific inputs, execution records, and P&L. Doctor Quant detects those fields and adapts the position chart and action receipt automatically.

The stocks deliberately do not trade together. AAPL uses RSI mean reversion, MSFT uses 20-day momentum, NVDA uses a volatility gate, JPM uses bank-fundamental signals, and XOM uses oil momentum and inventory information. Their decisions therefore occur at different times and produce different position paths.

### What to say and show

1. **Set the boundary.**

   > â€œDoctor Quant is a local, read-only forensic tool. It does not trade, change accounts, or invent a reason for a loss.â€

2. Click **Run complete CSV demo**. Choose a stock and show its position history. The line is how many shares were held; the coloured dots are the recorded BUY, SELL, and HOLD actions. Click anywhere on the line, then switch symbols to show that each strategy responds to different inputs.

   > â€œThis is the algorithmâ€™s position over timeâ€”not an abstract buy/sell score. Every point can be inspected.â€

3. In the action receipt, show the action, saved explanation, traded quantity, resulting position, and recorded P&L. Expand **What the algorithm knew** to show every retained indicator and when it was available.

   > â€œDoctor Quant reconstructs the latest action using only data available by the selected time. If the strategy adds or removes indicators, this list changes automatically.â€

4. Expand the verification details and show the evidence path:

   ```text
   observation â†’ decision â†’ target â†’ fill â†’ position â†’ P&L
   ```

   > â€œEach card is a retained record, and each arrow is an explicit parent-child linkâ€”not an AI-generated story.â€

5. Click each ledger card. Explain that its receipt identifies the event and why the step is supported. In the supplied example:

   | Step | Presentation evidence |
   | --- | --- |
   | Observation | A point-in-time earnings/valuation snapshot was retained at 09:25. |
   | Decision | The named model selected a `BUY` at 09:30 using that snapshot. |
   | Target | Portfolio construction requested 500 shares / 5.0% at 09:31. |
   | Fill | The order filled 500 shares at 09:32. |
   | Position | The custody position reconciled to that fill at 09:33. |
   | P&L | The 16:00 P&L mark belongs to that reconciled position. |

6. Point out the decision provenance receipt. It identifies the strategy version, model version, feature snapshot, action, and structured reasons.

   > â€œThis proves that the record chain is complete and time-valid. It does *not* prove that the model economically caused a loss. It proves exactly what Doctor Quant is permitted to say from the evidence.â€

### Suggested 90-second presentation script

> â€œDoctor Quant is a flight recorder for trading algorithms. The position line shows how many shares the algorithm held over time. I can click any point and see the latest action, why it acted, what actually traded, and every saved market or model input available beforehand. The dashboard is not tied to a fixed indicator list: it discovers the fields supplied by each strategy. Underneath, the evidence chain verifies that the observation, decision, target, fill, position, and P&L records really connect. If the file did not retain an action or input, Doctor Quant says so instead of inventing an explanation.â€

### Interpreting the result

| You see | It means | What to do next |
| --- | --- | --- |
| All `SUPPORTED` | The supplied records form a linked, time-valid lifecycle. | Investigate market, model, or policy quality without questioning record lineage. |
| `MISSING` | The relevant record or parent link was not supplied. | Export/retain the named decision, target, order/fill, or position record. |
| `CONTRADICTED` | A supplied parent ID or AI rationale conflicts with other retained evidence. | Resolve the source-system discrepancy; do not make a causal claim yet. |
| `TIME-INVALID` | Evidence was available only after the event it claims to support. | Exclude it from the decision-time explanation; retrieve the point-in-time version. |
| `INFERRED` | Doctor Quant has a bounded pattern-based hypothesis, not a proven link. | Treat it as an investigation lead and collect confirming evidence. |

### Complete-example format

The only bundled CSV is [`sample_data/full_product_demo.csv`](sample_data/full_product_demo.csv); the app loads it through **Run complete CSV demo**. It contains analytic inputs plus complete lifecycle IDs, so one file demonstrates strategy detection, point-in-time inputs, decisions, targets, fills, positions, P&L, replay, and the evidence ledger. The equivalent copyable JSON Evidence Bundle is [`examples/complete-evidence-ledger.json`](examples/complete-evidence-ledger.json), which can be submitted to `POST /api/evidence-bundle/validate`.

Every event needs these base fields:

```json
{
  "kind": "decision",
  "event_id": "decision-20250816-0930",
  "parent_id": "obs-earnings-20250816-0925",
  "timestamp": "2025-08-16T09:30:00Z"
}
```

`kind` must be one of `observation`, `decision`, `target`, `fill`, `position`, or `pnl`. `event_id` and `timestamp` are mandatory. Except for `observation`, each event should use `parent_id` to reference the event that immediately precedes it in the lifecycle. Add `available_at` to evidence whose availability matters; it must not be later than the decision it supports.

For an algorithm decision, retain at least `model_version`, `feature_snapshot_id`, `decision_timestamp`, `available_at`, `action`, and `decision_reason`. Record actual holdings as `position_quantity` (preferred), `actual_position`, or `position`; Doctor Quant falls back to `target_quantity`, `target_position`, or `target_weight` when actual holdings are unavailable.

Indicator names are not fixed. Any additional non-lifecycle columns on the observation/decision recordsâ€”such as `rsi_14`, `macro_regime`, `sentiment_score`, or proprietary factorsâ€”are discovered and shown under **What the algorithm knew**. Doctor Quant walks backward from the decision and uses the newest value whose `available_at` (or `timestamp`) is not later than the decision time. Post-decision execution and outcome fields are excluded.

### CSV versus an Evidence Bundle

The normal CSV workflow accepts P&L and market/strategy measurements. It can identify loss patterns and replay them without future data, but it cannot turn columns such as `alpha_score` or `target_actual_weight_gap_bps` into proof of a specific decision, order, or position.

Use an Evidence Bundle when you need the full ledger. A normal CSV will therefore commonly show:

```text
SUPPORTED observation â†’ MISSING decision â†’ MISSING target
â†’ MISSING fill â†’ MISSING position â†’ SUPPORTED P&L
```

That is an honest import result, not dropped data or a product failure.

### Demo workflow for the analysis/replay experience

1. Open Doctor Quant and click **Run complete CSV demo**.
2. Inspect the incident timeline and select a material loss.
3. Read the **Explanation built from your data** flow:
   ```text
   observed break â†’ decision/translation mechanism â†’ outcome
   ```
4. Use the replay control in that same section. It rebuilds the investigation using only records available by the selected point in time.
5. Check the displayed immutable **snapshot ID**.
6. Select a different loss, then reselect the first loss. The snapshot and explanation must return to the same values.
7. Export a reproducibility receipt when available.

The bundled CSV is synthetic. It demonstrates deterministic mechanics and a complete evidence workflow; it does not establish real broker, vendor, or market truth.

---

# Product architecture

## 1. The Evidence Ledger

Doctor Quant is being rebuilt around a typed decision-to-P&L evidence ledger. Every incident should be expressible as this chain:

```text
observation
â†’ decision
â†’ target
â†’ fill
â†’ position
â†’ P&L
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

`observed_at` alone is insufficient. Fundamentals, research data, market data, and AI outputs may be revised later; Doctor Quant needs the actual version that was available at decision time.

---

## 2. What Doctor Quant should diagnose

Doctor Quant should automatically construct a replayable investigation route for every incident, without a human drawing arrows.

### Evidence-complete route

When all records are present and reconcile:

```text
Vendor snapshot V-18 available at 09:25
â†’ model run M-492 decided at 09:30
â†’ target T-77 at 09:31
â†’ fill F-882 at 09:32
â†’ position P-19
â†’ P&L at 16:00
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

When the chain is incomplete, Doctor Quant must still render a useful investigation path:

```text
Observed P&L loss
â†’ candidate layer: data / decision / target translation / execution / market
â†’ missing evidence required to confirm or reject that route
â†’ bounded conclusion: hypothesis, not established cause
```

It must not show a blank panel and it must not call a generated route causal proof.

---

## 3. AI decision failure forensics

For an AI or ML-driven strategy, "why did it decide that?" requires more than a final score. Doctor Quant must retain the **decision provenance**.

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
| `score`, `rank`, `expected_return`, `confidence` | Captures the modelâ€™s expressed belief. |
| `feature_snapshot_id` / input hashes | Identifies exactly what the model saw. |
| `reason_codes` / feature contributions | Human-readable, structured rationaleâ€”not free-form post-hoc prose. |
| `raw_artifact_hash` | Allows evidence integrity checks. |

### AI failure classes Doctor Quant should distinguish

| Failure class | Evidence needed | Example conclusion |
| --- | --- | --- |
| Input/data failure | point-in-time vendor snapshots, availability times, revisions, feature hashes | â€œThe model used a stale/revised input.â€ |
| Model/policy failure | model version, features, score/rank, policy/prompt, decision record | â€œThe deployed model ranked this asset despite adverse supported inputs.â€ |
| Portfolio translation failure | decision, target, optimizer constraints, target output | â€œThe decision did not translate to the intended target.â€ |
| Execution failure | order/fill IDs, timestamps, price, fees, venue, slippage | â€œThe target was correct; execution diverged materially.â€ |
| Position/accounting failure | fill-position mapping, corporate actions, valuation marks | â€œThe reported P&L does not reconcile to the held position.â€ |
| Market/regime failure | benchmark/factor/exposure/market records available at time | â€œMarket movement explains observed loss; no data fault is supported.â€ |
| Explanation failure | model rationale versus actual inputs/policy/result | â€œThe claimed AI rationale contradicts retained decision evidence.â€ |

Doctor Quant should be able to say **where the AI failed** only when this evidence exists. If a model has no retained decision provenance, Doctor Quant may say:

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
5. Can a modelâ€™s rationale be tested against its actual retained inputs?

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

- local-only Windows and macOS startup;
- incident CSV and Incident Bundle validation paths;
- immutable snapshot IDs;
- no-lookahead replay;
- selected-loss race protection;
- reproducibility receipts and local Incident Command endpoint;
- additive attribution validation;
- automatic evidence-flow fallback with `supported`, `candidate`, and `gap` labels;
- typed Evidence Ledger foundation for:
  ```text
  observation â†’ decision â†’ target â†’ fill â†’ position â†’ P&L
  ```
- framework-neutral `StrategyRecorder` with accessed-input capture;
- callable, parameter, feature-snapshot, and raw-event fingerprints;
- automatic look-ahead rejection at the recorder boundary;
- linked fill, position, and P&L recording with ordering checks;
- configurable execution-field adapter for broker/OMS payloads;
- common connector contract for HTTP JSON, Python SDKs, CSV, JSON, JSONL, and custom sources;
- per-field source/version/timestamp/raw-response provenance;
- multi-source point-in-time merging with look-ahead and collision rejection;
- append-only memory, JSONL, and local HTTP sinks;
- recorded-strategy discovery and evidence replay in the dashboard;
- a runnable 360-event unfamiliar-strategy example;
- browser checks for demo load, console errors, and A â†’ B â†’ A selected-loss determinism.

Still required for production integrations:

- vendor-maintained adapters for specific brokers, OMSs, feature stores, and model registries;
- durable model-artifact and dependency-environment storage, not only fingerprints;
- corporate-action, fee, FX, partial-fill, amendment, and cancellation reconciliation;
- authentication, access control, retention policies, and production-scale ingestion;
- validated model-native contribution or counterfactual explanations where supported.

---

# Verification

Run the Python/API tests on Windows:

```powershell
py -3 -m unittest discover -s tests -q
```

Or on macOS:

```bash
python3 -m unittest discover -s tests -q
```

Check frontend syntax on either platform if Node.js is installed:

```powershell
node --check .\app.js
```

```bash
node --check app.js
```

Run the optional browser tests from the project folder:

```text
npx playwright test
```

A release claim requires all applicable checks to pass, plus the platform-specific health check documented under **Install and start Doctor Quant**.

---

# Accuracy boundary

Doctor Quant can make deterministic, reproducible claims about the records supplied to it:

- whether a link exists;
- whether it is time-valid;
- whether quantities/P&L reconcile;
- which model/data/decision artifact was supplied;
- what evidence is missing or contradictory.

Doctor Quant cannot establish real-world causal truth from synthetic data, missing provenance, or correlation alone.

```text
Complete record chain + reconciliation
â‰  universal proof of economic causality

Missing record chain
â‰  permission to invent a causal narrative. 
```

That restraint is the point. Doctor Quant is not meant to make losses sound explained; it is meant to make the evidence trail impossible to bluff.
