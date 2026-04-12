# QuantMetrics OS

**Orchestration layer for a systematic multi-asset trading suite — QuantBuild, QuantBridge, QuantLog.**

This repository is the **front door**: one place to resolve paths, environment, and subprocess entrypoints so research, execution, and observability run as a single system — not three disconnected scripts.

*Nederlandstalige details en handouts: zie [`docs/`](docs/).*

### Suite repositories (GitHub)

| Component | Repository |
| --- | --- |
| **QuantMetrics OS** (this repo) | [roelofgootjesgit/quantmetrics_os](https://github.com/roelofgootjesgit/quantmetrics_os) |
| **QuantBuild** | [roelofgootjesgit/quantbuildE1](https://github.com/roelofgootjesgit/quantbuildE1) |
| **QuantBridge** | [roelofgootjesgit/quantBridge-v.1](https://github.com/roelofgootjesgit/quantBridge-v.1) |
| **QuantLog** | [roelofgootjesgit/quantlog-v.1](https://github.com/roelofgootjesgit/quantlog-v.1) |

*Fork under another user? Update links or use `GITHUB_USER` in [`scripts/clone_quant_suite.sh`](scripts/clone_quant_suite.sh).*

---

## Suite snapshot

Static badges (update URLs/query strings when you publish new validation numbers):

[![Tests](https://img.shields.io/badge/tests-99%20passing-22c55e?style=flat-square)](docs/SHOWCASE.md)
[![Profit factor](https://img.shields.io/badge/profit%20factor-5.24-0ea5e9?style=flat-square)](docs/SHOWCASE.md)
[![Win rate](https://img.shields.io/badge/win%20rate-70%25-8b5cf6?style=flat-square)](docs/SHOWCASE.md)
[![Max DD](https://img.shields.io/badge/max%20DD-%E2%88%927.1%25-f97316?style=flat-square)](docs/SHOWCASE.md)
[![FTMO MC](https://img.shields.io/badge/FTMO%20MC%20pass-51.4%25-64748b?style=flat-square)](docs/SHOWCASE.md)

| Metric | Value |
| --- | --- |
| Tests | 99 passing |
| Profit factor | 5.24 |
| Win rate | 70% |
| Max drawdown | −7.1% |
| FTMO Monte Carlo pass rate | 51.4% |

### Equity curve (QuantBuild)

Cumulative R from a reproducible XAUUSD backtest (`strict_prod_v2`, ~5y). Regeneration steps live in the **QuantBuild** repository README; this copy is for suite-level storytelling when someone lands on OS first:

![QuantBuild backtest equity (cumulative R)](docs/assets/equity_curve_5y.png)

---

## Architecture

![QuantMetrics suite architecture](docs/assets/quantmetrics-suite-architecture.svg)

<details>
<summary>Plain-text diagram (fallback)</summary>

```
                    ┌──────────────────┐
                    │  QuantMetrics OS  │  paths, env, unified CLI
                    └─────────┬────────┘
                              │
   Market data ───────────────┼──────────────────────────────┐
                              ▼                              │
                    ┌──────────────────┐                     │
                    │    QuantBuild    │  signals, risk,    │
                    │                  │  strategy loop     │
                    └─────────┬────────┘                     │
                              ▼                              │
                    ┌──────────────────┐                     │
                    │   QuantBridge    │  broker execution, │
                    │                  │  cTrader / IC path │
                    └─────────┬────────┘                     │
                              ▼                              │
                    ┌──────────────────┐                     │
                    │    QuantLog      │  JSONL events,      │
                    │                  │  validate, reports  │
                    └─────────┬────────┘                     │
                              └──────── post-run analysis──┘
```

</details>

---

## What each component proves

| Component | What it demonstrates |
| --- | --- |
| **QuantMetrics OS** | You treat the stack as **production software**: explicit wiring, reproducible launches, and a clear seam between orchestration and domain code. |
| **QuantBuild** | **Systematic edge**: backtests, risk gates, prop-style constraints (e.g. FTMC), and a test-backed signal/risk core — not a discretionary script. |
| **QuantBridge** | **Real execution discipline**: broker integration, smoke/regression paths, and operational concerns (reconnect, health) separated from alpha. |
| **QuantLog** | **Auditability**: append-only structured events, validation, and day-level scoring — the feedback loop that turns logs into improvements. |

---

## What lives in *this* repo

| Path | Role |
| --- | --- |
| `orchestrator/quantmetrics.py` | Loads `orchestrator/.env`, resolves sibling repo roots, runs `python -m …` and scripts with correct `cwd` / `PYTHONPATH`. |
| `orchestrator/qm.ps1` | Windows-friendly wrapper. |
| `orchestrator/config.example.env` | Template for `QUANTBUILD_ROOT`, `QUANTBRIDGE_ROOT`, `QUANTLOG_ROOT`, optional `PYTHON`, configs. |
| `orchestrator/config.vps.example.env` | VPS / Linux layout hints. |
| `vscode/quant-suite.code-workspace` | Multi-root workspace (OS + Build + Bridge + Log). |
| `scripts/clone_quant_suite.sh` | Optional clone/update helper and baseline `.env`. |
| `docs/` | Roadmap, sprint plan, suite handouts. |

Strategy, broker adapters, and event schemas live in the **sibling repositories**, not here.

---

## Quick start

**Layout** (sibling folders under one parent):

```text
<parent>/
  quantmetrics_os/     ← this repo
  quantbuildv1/
  quantbridgev1/
  quantlogv1/
```

**Steps**

1. Copy `orchestrator/config.example.env` → `orchestrator/.env` and set the three `*_ROOT` paths.
2. From `orchestrator/`:

   ```powershell
   python quantmetrics.py check
   ```

   On Windows you can use `.\qm.ps1 check`.

3. Examples:

   | Goal | Command |
   | --- | --- |
   | Show resolved paths | `python quantmetrics.py check` |
   | QuantBuild live (paper; no `--real`) | `python quantmetrics.py build -c configs/strict_prod_v2.yaml` |
   | QuantBridge smoke (mock) | `python quantmetrics.py bridge smoke --mode mock` |
   | QuantLog validate events | `python quantmetrics.py log validate-events -- --path <day-folder>` |
   | After a session | `python quantmetrics.py post-run YYYY-MM-DD` |

Use `python quantmetrics.py --help` and per-subcommand `--help` for full options.

**QuantBuild + live bridge:** set `QUANTBRIDGE_SRC_PATH` to QuantBridge’s `src` directory so Build can load the bridge module — see [Suite start handout](docs/SUITE_START_HANDOUT.md).

---

## Requirements

- Python on the host (or per-repo venvs); override with `PYTHON` in `.env` if needed.
- Cloned **QuantBuild**, **QuantBridge**, and **QuantLog** repos with paths in `.env`.

---

## Documentation

- [GitHub profile README (template to paste)](docs/GITHUB_PROFILE_README.md) — landing page for `github.com/<you>/<you>`.
- [Suite showcase (technical CV)](docs/SHOWCASE.md) — problem, architecture rationale, validation, deployment roadmap.
- [Suite start (handout)](docs/SUITE_START_HANDOUT.md) — `.env`, common commands, workspace, `QUANTBRIDGE_SRC_PATH`.
- [Roadmap](docs/Roadmap_os.md)
- [Sprint plan](docs/QUANTMETRICS_SPRINT_PLAN.md)
