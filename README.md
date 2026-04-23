# QuantMetrics Suite

> A disciplined, modular trading infrastructure: orchestrate, decide, execute, observe, measure, analyze, and iterate — with explicit boundaries and auditability.

If you are evaluating this as a collaborator, allocator, or senior engineer: this repo is meant to read like **infrastructure**, not a “strategy repo”.

---

## At a glance

- **What this is**: a coordinated stack for controlled iteration under real operational constraints
- **What this is not**: a single script “alpha”, a black box, or a claim about profitability
- **Why monorepo**: one review surface for cross-layer changes while preserving module ownership
- **How trust is earned**: separation of concerns, append-only logs, reproducible artifacts, and failure containment

---

## Who this is for

- **Engineering partners** who want clean boundaries, testable layers, and operational rigor
- **Capital / risk stakeholders** who want traceability and controlled change management
- **Researchers** who want experiment discipline (baseline required, comparable windows, artifacts)

---

## The operating thesis

Markets are noisy. The suite is built to separate:

- **decision quality** (what should happen, under which constraints)
- **execution reality** (what actually happened, with broker-specific behavior)
- **measurement** (what can be proven from logs and artifacts)
- **research governance** (what we tested, what we learned, what we do next)

The goal is not to “sound smart”. The goal is to make performance attribution **defensible**.

---

## End-to-end stack flow

1. `quantmetrics_os/` is the suite front door: paths, environment, orchestration, and standardized entrypoints across modules.
2. `quantbuild/` converts market context into constrained trade decisions.
3. `quantbridge/` translates decisions into broker-facing execution actions.
4. `quantlog/` records immutable operational events across the lifecycle.
5. `quantanalytics/` analyzes outcomes and produces diagnostics from logged reality.
6. `quantresearch/` frames hypotheses, tracks experiments, and records auditable conclusions tied to artifacts (what to test next, and why).
7. The loop closes back into `quantmetrics_os/` and `quantbuild/` (configs, constraints, and operating parameters), without mixing responsibilities across layers.

One-line mental model:

Suite orchestration → Decision → Execution → Logging → Analytics → Research conclusions → Improvement

---

## System boundary (hard lines)

This is not a monolith pretending to be modular. Each folder is a **contract**.

| Layer | Owns | Explicitly does not own |
|---|---|---|
| `quantmetrics_os/` | Orchestration, paths, suite entrypoints | Strategy logic, broker execution |
| `quantbuild/` | Decisions + risk constraints | Broker connectivity, append-only event storage |
| `quantbridge/` | Execution routing + broker integration | Strategy generation, analytics |
| `quantlog/` | Append-only event capture + audit trail | Decisioning, broker routing |
| `quantanalytics/` | Diagnostics from logs/metrics outputs | Live execution |
| `quantresearch/` | Experiment registry + comparisons + conclusions | Live execution |

This separation is how you keep failures **localized** and systems **testable**.

---

## Decision integrity and control

Design constraints that show up across the suite:

- **Explicit gating** before capital is exposed
- **Reproducibility**: same inputs should yield the same decision artifacts (within defined boundaries)
- **Attribution hygiene**: separate “decision quality” from “execution noise” before drawing conclusions

---

## Failure-aware design

The stack is built to degrade safely:

- decision and execution remain isolated
- risk controls can tighten without rewriting execution plumbing
- logging and analytics remain available for post-incident diagnosis

The priority is **continuity, containment, recoverability**.

---

## Quick start

```bash
git clone https://github.com/roelofgootjesgit/QuantMetrics-Suite.git QuantMetrics-Suite
cd QuantMetrics-Suite

# inspect the full stack
ls

# typical navigation
cd quantmetrics_os
# or
cd quantbuild
```

---

## Working model (how we collaborate)

1. Work from repo root for cross-module visibility.
2. Keep changes scoped to the owning module whenever possible.
3. Validate with module-level tests before cross-module PRs.
4. Use one PR when a change intentionally crosses boundaries.

---

## Documentation map

- Root `README.md`: positioning, boundaries, and navigation
- Module `README.md` files: setup, operations, testing, and local conventions
- Module `docs/` directories: deep technical specifications and runbooks

---

## Migration note

The monorepo was assembled via `git subtree` imports, preserving history from the original repositories.
