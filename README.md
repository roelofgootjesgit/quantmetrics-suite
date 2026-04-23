# Quant Metrics Suite

> Controlled quant infrastructure for research, decision, execution, logging, metrics, and analysis.

`quantmetrics-suite` is the unified monorepo for the complete Quant stack.  
It covers the full operating chain from hypothesis and experimentation through execution, logging, measurement, and post-trade analysis, with strict ownership per layer.

## System role

The suite operates as one controlled end-to-end system:

Hypothesis → Market Data → Decision → Execution → Logging → Metrics → Analytics → Research conclusions → Improvement

The objective is not to claim edge by narrative, but to evaluate decision quality under real operating conditions.

## End-to-end stack flow

1. `quantresearch/` registers hypotheses, compares runs, and produces auditable research conclusions tied to artifacts.
2. `quantbuildv1/` converts market context into constrained trade decisions.
3. `quantbridgev1/` translates decisions into broker-facing execution actions.
4. `quantlogv1/` records immutable operational events across the lifecycle.
5. `quantmetrics_os/` assembles run artifacts, comparisons, and experiment outputs.
6. `quantanalyticsv1/` analyzes outcomes and feeds improvements back into decision design.

This is one looped stack, not six disconnected repositories.

## System boundary

This repository does not represent one monolith. It represents coordinated layers with isolated ownership.

Each module is responsible for its own domain:
- `quantresearch/`: hypothesis registry, comparisons, and research knowledge artifacts
- `quantbuildv1/`: decision logic and risk constraints
- `quantbridgev1/`: execution routing and broker connectivity
- `quantlogv1/`: append-only event logging and traceability
- `quantmetrics_os/`: experiment runs, metrics, and artifact orchestration
- `quantanalyticsv1/`: post-trade analysis and insight generation

This separation ensures:
- deterministic behavior per layer
- testability of each responsibility
- containment of failures without cross-layer corruption

## Decision integrity and control

Across the suite, components are built to reduce randomness leakage:
- explicit gating before action
- reproducible outputs from the same inputs
- strict separation between decision quality and execution effects

Performance interpretation is therefore tied to system behavior, not incidental noise.

## Failure-aware design

The architecture is built to degrade safely under stress:
- decision and execution remain isolated
- risk controls can tighten without changing execution plumbing
- logging and analytics remain available for post-event diagnosis

The priority is continuity, containment, and recoverability.

## Suite map

| Module | Core responsibility | Not responsible for |
|---|---|---|
| `quantresearch/` | Experiment registry, comparisons, and research conclusions | Live execution and broker connectivity |
| `quantbuildv1/` | Decisions and risk logic | Order execution and event storage |
| `quantbridgev1/` | Broker/execution integration | Strategy generation and analytics |
| `quantlogv1/` | Event capture and audit trail | Decisioning and broker routing |
| `quantmetrics_os/` | Metrics runs and artifact management | Execution routing and raw decision logic |
| `quantanalyticsv1/` | Analysis and reporting | Live execution and broker connectivity |

## Quick start

```bash
git clone https://github.com/roelofgootjesgit/quantmetrics-suite.git
cd quantmetrics-suite
# inspect the full stack
ls

# start with research governance, then move through the runtime stack as needed
cd quantresearch

# or jump directly into the decision layer
cd quantbuildv1
```

## Working model

1. Work from repo root for cross-module visibility.
2. Keep changes scoped to the owning module whenever possible.
3. Validate with module-level tests before cross-module PRs.
4. Use one PR when a change intentionally crosses boundaries.

## Documentation

- Root `README.md`: architecture intent and module boundaries
- Module `README.md` files: setup, operations, testing, and conventions
- Module `docs/` directories: deep implementation notes

## Migration note

The monorepo was assembled via `git subtree` imports, preserving history from original repositories.
