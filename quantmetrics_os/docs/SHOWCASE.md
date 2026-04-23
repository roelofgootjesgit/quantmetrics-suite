# Quant suite — showcase (QuantOS + siblings)

Technical overview for recruiters, clients, and collaborators: **what problem this stack solves**, **why it is structured this way**, **what has been validated**, and **where deployment is headed**.

This document complements the [root README](../README.md) (quick orientation) and the [suite handout](SUITE_START_HANDOUT.md) (day-to-day commands).

---

## 1. Problem the suite solves

Discretionary trading and one-off scripts do not scale: edge is hard to separate from luck, execution drift is invisible, and post-trade learning is usually anecdotal.

The Quant suite aims to make systematic trading **testable**, **executable**, and **auditable**:

- **Testable** — hypotheses and risk rules live in code with automated checks and backtests (**QuantBuild — Signal Engine**).
- **Executable** — broker-facing logic is isolated, smoke-tested, and regression-tested (**QuantBridge — Execution Engine**).
- **Auditable** — decisions and fills become structured events that can be validated, summarized, and scored (**QuantLog — Observability Layer**).

**QuantOS — Orchestrator** (this repo, folder `quantmetrics_os/`) is the orchestration layer: one entry surface for paths, environment, and subprocess launches so the three domains run as a **single system** instead of three disconnected checkouts.

---

## 2. Architecture choices (and why)

| Choice | Rationale |
| --- | --- |
| **Separate repositories** | Clear ownership boundaries: research vs execution vs logging evolve at different cadences; dependencies stay explicit. |
| **OS repo without strategy/broker code** | Orchestration stays thin and stable; domain code does not pollute “how to start the suite.” |
| **Subprocess-based orchestration** | Each component keeps its own `PYTHONPATH`, venv, and CLI; OS composes them without importing their internals. |
| **Append-only event log** | Historical truth for disputes, debugging, and research replay; aligns with serious observability practice. |
| **Explicit `.env` for roots** | Reproducible layout across laptops, VPS, and CI; no hard-coded machine paths in shared docs. |

Trade-offs (acknowledged): more repos to clone, and `QUANTBRIDGE_SRC_PATH`-style bridges when Build must load Bridge dynamically — documented in the handout.

---

## 3. Validation results (representative)

Figures below are **published as static suite-level metrics** in the OS README; refresh them when you cut a new validation or release. They are meant to show the *class* of evidence (tests, prop-style stress, performance metrics), not to imply live trading performance.

| Area | Indicator (example values) |
| --- | --- |
| Regression safety | ~99 automated tests passing (QuantBuild and related CI) |
| Backtest quality | Profit factor, win rate, max drawdown from controlled backtests (e.g. PF ~5.2, WR ~70%, MDD ~−7%) |
| Prop-style stress | FTMO-style Monte Carlo pass rate (~51% in published example) |

**Equity curve:** see `docs/assets/equity_curve_5y.png` in this repo (synced copy). Regenerate from QuantBuild with `scripts/export_equity_chart.py` (same PNG is written under `quantbuildv1/docs/assets/` and copied to **`quantmetrics_os/docs/assets/`** when the QuantOS sibling folder exists). Caption in the READMEs distinguishes **multi-instrument headline metrics** from this **single-config XAUUSD** chart.

---

## 4. Deployment roadmap (high level)

| Phase | Focus |
| --- | --- |
| **Local / dev** | Sibling repos + `orchestrator/.env` + `quantmetrics.py check`; VS Code multi-root workspace. |
| **Paper / demo** | QuantBuild without `--real`; Bridge smoke (mock/OpenAPI) against demo accounts as configured. |
| **VPS / unattended** | See `orchestrator/config.vps.example.env`; systemd or equivalent wrapping `quantmetrics` entrypoints; secrets outside git. |
| **Hardening** | Stricter configs, alerting (e.g. Telegram where wired), expanded QuantLog scoring and dashboards as needed. |

Details and sprint alignment: [Roadmap_os.md](Roadmap_os.md), [QUANTMETRICS_SPRINT_PLAN.md](QUANTMETRICS_SPRINT_PLAN.md).

---

## 5. Where to go next

- **Run the suite:** [SUITE_START_HANDOUT.md](SUITE_START_HANDOUT.md)
- **Repo map and CLI:** [README](../README.md)
- **GitHub (repo slugs):**
  - [`quantmetrics_os`](https://github.com/roelofgootjesgit/quantmetrics_os)
  - [`quantbuildv1`](https://github.com/roelofgootjesgit/quantbuildv1)
  - [`quantbridgev1`](https://github.com/roelofgootjesgit/quantbridgev1)
  - [`quantlogv1`](https://github.com/roelofgootjesgit/quantlogv1)
  - [`quantanalyticsv1`](https://github.com/roelofgootjesgit/quantanalyticsv1)

---

*Last updated: align validation numbers and equity image with your current QuantBuild exports before sharing externally.*
