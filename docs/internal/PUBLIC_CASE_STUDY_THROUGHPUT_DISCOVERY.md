# Case Study: Throughput Discovery

## Claim

We do not claim edge. We evaluate whether the system can prove it.

QuantMetrics treats a strategy as a **measurement problem**: every run produces structured evidence (hypothesis -> plan -> runs -> analytics -> discovery -> verdicts -> decision -> lineage). If the evidence does not clear the bar, the product says so-and records **where** throughput and opportunity diverge.

## Problem

On a multi-year, production-shaped configuration, headline performance looked supportive (for example, positive closed-trade expectancy and profit factor on the order of **~0.4 R** and **~1.75 PF** with **n ~= 45** trades in one canonical bundle), yet the same bundle still landed in **`VALIDATION_REQUIRED`**: confidence stayed **LOW**, sample size stayed **below promotion thresholds**, and automated warnings flagged **guard dominance** (risk lockdown shaping the funnel more than the entry model).

A narrower calendar slice on the same rule stack can look even worse-not because the "edge disappeared," but because **throughput collapses** and the surviving sample is too small to interpret.

So the real question is not "did we make money in the backtest?" but **"which layer-filters, guards, regime, session-ate the opportunity, and is any relaxation defensible?"**

## Method

We ran an **A/B-style matrix**: same strategy quality engine (SQE) and guard semantics, **controlled changes** to horizon and throughput (for example baseline calendar window vs multi-year windows vs expanded relaxation experiments), each producing:

- Immutable **quantlog** event streams
- **Analytics** bundles (edge report, guard attribution, throughput, verdicts)
- Explicit **promotion** decisions with failed rule reasons

No hand-waved "we relaxed filters until it worked." Each variant is a separate run with its own decision record.

## Findings

- **Filter kill ratio.** In an expanded-window experiment, throughput analytics showed roughly **two thirds** of candidate cycles filtered or blocked before execution (`filter_kill_ratio ~= 0.65` on **167** raw cycles -> **58** executed in `quantmetrics_os/runs/EXP-2025-5year-expanded/single/analytics/throughput.json`). That is a direct answer to "where did the trades go?"-not a story about alpha.

- **Watchlist cluster.** Guard attribution and funnel warnings cluster on the same families of blocks (for example **`regime_allowed_sessions`** and related session/regime gates accounting for a large share of **BLOCK** decisions in key-findings summaries). That gives a **prioritized research queue**: you do not optimize entries until you know whether the book is closed by calendar, regime, or risk caps.

- **No relax-candidate.** Relaxing time or filters without a pre-registered hypothesis increases **false discovery risk**. In this program, no variant produced a bundle that simultaneously cleared **sample size**, **confidence**, **warning hygiene**, and **promotion rules**. The system's job is to refuse a shortcut narrative.

- **No promotion.** Representative outcomes: **`VALIDATION_REQUIRED`** when expectancy and PF look fine but **n < 100**, confidence **LOW**, and major warnings persist (`quantmetrics_os/runs/EXP-2025-5year/single/analytics/PROMOTION_DECISION.md`); and hard **`REJECT`** when the narrow-window slice collapses to a tiny trade count with negative expectancy (`quantmetrics_os/runs/EXP-2025-baseline/single/analytics/PROMOTION_DECISION.md`).

## Conclusion

The system **blocked overclaiming**: positive headline metrics did not automatically imply deployable edge. It also **named the bottleneck**-throughput loss to guards/filters and insufficient statistical mass-not a vague "model needs work."

The next research direction is therefore **actionable**: design targeted experiments on the dominant blockers (session/regime throughput, caps, stability across regimes) under the same evidence contract, instead of tuning indicators in the dark.

## Why this matters

Most trading bots optimize blindly and ship a curve. QuantMetrics produces **auditable decision evidence**: what was tested, what passed or failed which rules, and which layer of the stack consumed opportunity.

That is the bridge from "I built a quant stack" to **"I can debug your trading system as a measurement and governance problem-and prove what blocked promotion."**
