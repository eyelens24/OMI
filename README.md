# Doctor Quant — Decision-to-P&L Incident Forensics

[Click here to test demo](https://doctorquant.onrender.com)
Demo may take up to a minute to load, please be patient.

Doctor Quant is a **forensic tool** for investigating trading incidents — moments where an algorithm made a decision and someone needs to know why.

It is **not** a trading bot, broker terminal, or execution tool. It never places orders and never touches a live account.

## The core question

For any point in a position's history, Doctor Quant answers:

> What did the algorithm know? What did it decide? What did it intend to do? What actually happened? And what evidence connects each of those steps to the final P&L?

It packages the answer into a single **Decision Receipt**:

```
position before → BUY / SELL / HOLD → why → what was known beforehand
→ intended size → actual execution → position after → P&L → trust status
```

## The guiding principle: no evidence, no story

Doctor Quant refuses to make up a tidy explanation. It only shows the rationale and data that were actually retained at decision time, then labels the chain connecting them as one of:

| Status | Meaning |
|---|---|
| **Supported** | The records link together and check out — no gaps. |
| **Missing** | A required record was never supplied. |
| **Contradicted** | Two records disagree with each other. |
| **Time-invalid** | A piece of evidence only existed *after* the decision it's supposedly explaining (lookahead). |
| **Inferred** | A reasonable hypothesis from patterns — not a proven fact. |

A fluent-sounding story is not proof. If the evidence isn't there, Doctor Quant says so instead of inventing a cause.

## How an investigation is structured

Every incident is treated as a chain of six kinds of evidence:

```
observation → decision → target → fill → position → P&L
```

- **Observation** — a data point available to the algorithm (a price, a fundamental, a sentiment score).
- **Decision** — the algorithm's choice, and its stated reason.
- **Target** — the position size it intended to reach.
- **Fill** — what actually got executed.
- **Position** — the resulting holdings.
- **P&L** — the outcome.

Doctor Quant walks this chain and checks each link. A key rule: a piece of evidence can only support a decision if it was actually available *before* that decision was made (`available_at <= decision_timestamp`). Data that was revised or published later doesn't count, even if it "looks like" it should have been known.

## What it looks like in use

The bundled demo loads five independent strategies (AAPL/RSI, MSFT/momentum, NVDA/volatility, JPM/fundamentals, XOM/oil signals), each with its own position history. Clicking any point on a strategy's position line surfaces:

- the **action** taken (buy/sell/hold) and the **reason** recorded for it
- **what the algorithm knew** — every indicator available at that moment
- the full **evidence chain**, card by card, with each link's status
- a **replay** view that reconstructs the investigation using only evidence that existed by a chosen point in time — reproducible, not regenerated from scratch each time

## Diagnosing AI/model-driven decisions

For an algorithm driven by a model, "why did it do that" needs more than a final score — it needs **decision provenance**: which model version, which exact inputs, which parameters, and a structured (not just narrative) reason.

Doctor Quant distinguishes between different kinds of failure, depending on what evidence exists:

| Failure type | What it looks like |
|---|---|
| **Input/data failure** | The model used stale or since-revised data. |
| **Model/policy failure** | The model made a call that its own inputs don't support. |
| **Portfolio translation failure** | The decision didn't turn into the intended target position. |
| **Execution failure** | The target was right, but the fill diverged from it. |
| **Accounting failure** | The reported P&L doesn't reconcile with the actual position. |
| **Market failure** | The loss is explained by the market, not by anything the algorithm did wrong. |
| **Explanation failure** | The model's stated rationale contradicts its own recorded inputs. |

If a model's decisions weren't recorded with enough detail, Doctor Quant won't guess — it reports plainly that the cause can't be established from what's available.

## CSV vs. a full Evidence Bundle

A simple CSV of timestamps and P&L is enough for statistical analysis and replay, but it can't prove a specific decision → order → position chain — for that, Doctor Quant needs a full **Evidence Bundle** with all six event types and their linking IDs. Using a plain CSV instead is still useful, it just honestly shows more of the chain as "missing" rather than "supported."

## What Doctor Quant can and can't claim

**Can:** whether a link in the evidence chain exists, whether it's time-valid, whether the numbers reconcile, and exactly what's missing or contradictory.

**Can't:** prove real-world economic cause-and-effect from a complete record chain alone, or from correlation, or from synthetic data.

```
Complete record chain + reconciliation  ≠  proof of economic causality
Missing record chain                    ≠  permission to invent a story
```

That restraint is the whole point — Doctor Quant isn't built to make a loss sound explained. It's built to make the evidence trail impossible to fake.
