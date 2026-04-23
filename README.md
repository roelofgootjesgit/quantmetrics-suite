# QuantMetrics Suite

> We don’t claim edge — we build the infrastructure that makes edge **testable**.

A modular trading stack designed to **evaluate, execute, observe, measure, analyze, and improve** decision processes under real constraints — with strict ownership per layer.

Read this as **infrastructure**, not a “strategy repo”.

## TL;DR (10 seconds)

| You get | In practice |
|---|---|
| Orchestration | `quantmetrics_os/` standardizes how the suite is run, wired, and operated |
| Decision engine | `quantbuild/` produces constrained decisions (risk + rules), not broker calls |
| Execution boundary | `quantbridge/` owns broker connectivity and order lifecycle |
| Source of truth | `quantlog/` append-only event trail across the lifecycle |
| Diagnostics | `quantanalytics/` turns logs/metrics into actionable performance views |
| Research governance | `quantresearch/` tracks experiments, baselines, comparisons, and conclusions |
| Monorepo benefit | one review surface for cross-layer changes without melting boundaries |

Non-goals: black-box signals, “trust me” backtests, hidden state, or profitability marketing.

## Who this is for

- **Engineering partners** who care about boundaries, testability, and operational rigor
- **Capital / risk stakeholders** who want auditability and controlled change
- **Researchers** who want baseline discipline, comparable windows, and artifact-backed conclusions

## What problem this solves

Markets are uncertain. The suite is built to answer a narrower, harder question:

> Does this decision process behave as intended under real execution conditions — and where does expectancy come from (or disappear)?

Not “does the backtest look good”, but **does it survive execution, costs, constraints, and noise** — with attribution you can defend.

## What “edge” means here (no fairy tales)

The suite does not assume alpha.

It enforces the preconditions to **discover, validate, or reject** edge with integrity:

- **Decision integrity**: explicit gating, reproducible decision paths, no implicit “magic state”
- **Execution realism**: measure what the broker actually did (fills, rejects, latency), separately from the model
- **Attribution clarity**: decompose outcomes into decision vs execution vs regime effects
- **Controlled iteration**: changes ship as experiments with artifacts, not vibes

## End-to-end stack flow

1. `quantmetrics_os/` — orchestration, environment, standardized entrypoints
2. `quantbuild/` — decision engine (signals + constraints)
3. `quantbridge/` — execution routing and broker integration
4. `quantlog/` — immutable event logging (source of truth)
5. `quantanalytics/` — diagnostics and performance analysis
6. `quantresearch/` — experiment tracking and conclusions

Loop:

**Orchestration → Decision → Execution → Logging → Analysis → Research → Improvement**

## System boundary (hard separation)

Each module is a contract.

| Layer | Owns | Explicitly does not own |
|---|---|---|
| `quantmetrics_os/` | orchestration | strategy logic |
| `quantbuild/` | decisions + constraints | execution |
| `quantbridge/` | execution | strategy |
| `quantlog/` | event storage | decisions |
| `quantanalytics/` | analysis | execution |
| `quantresearch/` | experiments | live trading |

Why this matters: **failure containment**, **testability**, **controlled iteration**.

## Decision integrity (quality bar)

- explicit gating before capital exposure
- reproducible decision paths (within defined boundaries)
- separation of model output vs execution outcome
- traceability: decisions and outcomes are replayable from logs/artifacts

## Failure-aware design

- decision and execution are isolated
- risk constraints can tighten independently of broker plumbing
- logging remains available for diagnosis
- failures are observable and replayable

Priority: **continuity, containment, recoverability**.

## Quick start

```bash
git clone https://github.com/roelofgootjesgit/QuantMetrics-Suite.git QuantMetrics-Suite
cd QuantMetrics-Suite
ls

cd quantmetrics_os
# or
cd quantbuild
```

## Working model

1. Work from repo root for full visibility
2. Keep changes scoped to module ownership
3. Validate locally before cross-module changes
4. Use a single PR only when boundaries are intentionally crossed

## Documentation

- Root `README.md`: positioning + boundaries
- Module `README.md`: setup + usage
- `docs/`: specifications, runbooks, internal design

## Migration note

This monorepo was assembled using `git subtree`, preserving history from the original repositories.
