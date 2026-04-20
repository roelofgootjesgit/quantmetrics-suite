# quantmetrics_os

**Orchestrator for the Quant suite:** sibling checkouts **`quantbuildv1`** (signals/risk), **`quantbridgev1`** (execution), **`quantlogv1`** (JSONL observability), **`quantanalyticsv1`** (read-only JSONL analytics).

This repository is the **front door**: one place to resolve paths, environment, and subprocess entrypoints so research, execution, and observability run as a single system — not three disconnected scripts. *(Older docs may say “QuantMetrics OS”; same repo.)*

**Clone folder on disk:** `quantmetrics_os/` (matches the default GitHub repo name until you rename the remote).

*Nederlandstalige details en handouts: zie [`docs/`](docs/).*

### Suite repositories (GitHub)

| Repo | Remote |
| --- | --- |
| `quantmetrics_os` (**this**) | [roelofgootjesgit/quantmetrics_os](https://github.com/roelofgootjesgit/quantmetrics_os) |
| `quantbuildv1` | [roelofgootjesgit/quantbuildv1](https://github.com/roelofgootjesgit/quantbuildv1) |
| `quantbridgev1` | [roelofgootjesgit/quantbridgev1](https://github.com/roelofgootjesgit/quantbridgev1) |
| `quantlogv1` | [roelofgootjesgit/quantlogv1](https://github.com/roelofgootjesgit/quantlogv1) |
| `quantanalyticsv1` | [roelofgootjesgit/quantanalyticsv1](https://github.com/roelofgootjesgit/quantanalyticsv1) |

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

### Equity curve (`quantbuildv1`)

Cumulative R from a reproducible XAUUSD backtest (`strict_prod_v2`, ~5y). Regeneration steps live in the **`quantbuildv1`** README; this copy is for suite-level storytelling when someone lands here first:

![quantbuildv1 backtest equity (cumulative R)](docs/assets/equity_curve_5y.png)

---

## Architecture

![Quant suite architecture](docs/assets/quantmetrics-suite-architecture.svg)

<details>
<summary>Plain-text diagram (fallback)</summary>

```
                    ┌────────────────────┐
                    │  quantmetrics_os   │  paths, env, unified CLI
                    └─────────┬──────────┘
                              │
   Market data ───────────────┼──────────────────────────────┐
                              ▼                              │
                    ┌────────────────────┐                     │
                    │   quantbuildv1     │  signals, risk,    │
                    │                    │  strategy loop     │
                    └─────────┬──────────┘                     │
                              ▼                              │
                    ┌────────────────────┐                     │
                    │  quantbridgev1     │  broker execution, │
                    │                    │  cTrader / IC path │
                    └─────────┬──────────┘                     │
                              ▼                              │
                    ┌────────────────────┐                     │
                    │    quantlogv1      │  JSONL events,      │
                    │                    │  validate, reports  │
                    └─────────┬──────────┘                     │
                              └──────── post-run ──► quantanalyticsv1 (JSONL) ───┘
```

</details>

---

## What each repo proves

| Repo | What it demonstrates |
| --- | --- |
| `quantmetrics_os` | You treat the stack as **production software**: explicit wiring, reproducible launches, and a clear seam between orchestration and domain code. |
| `quantbuildv1` | **Systematic edge**: backtests, risk gates, prop-style constraints (e.g. FTMC), and a test-backed signal/risk core — not a discretionary script. |
| `quantbridgev1` | **Execution discipline**: broker integration, smoke/regression paths, and operational concerns (reconnect, health) separated from alpha. |
| `quantlogv1` | **Auditability**: append-only structured events, validation, and day-level scoring — the feedback loop that turns logs into improvements. |
| `quantanalyticsv1` | **Post-run insight** (read-only): funnel, no-trade reasons, and performance summaries from the same JSONL as `quantlogv1` — no mutation of logs. |

---

## What lives in *this* repo

| Path | Role |
| --- | --- |
| `orchestrator/quantmetrics.py` | Loads `orchestrator/.env`, resolves sibling repo roots, runs `python -m …` and scripts with correct `cwd` / `PYTHONPATH`. |
| `orchestrator/qm.ps1` | Windows-friendly wrapper. |
| `orchestrator/config.example.env` | Template for `QUANTBUILD_ROOT`, `QUANTBRIDGE_ROOT`, `QUANTLOG_ROOT`, optional `PYTHON`, configs. |
| `orchestrator/config.vps.example.env` | VPS / Linux layout hints. |
| `vscode/quant-suite.code-workspace` | Multi-root workspace (OS + Build + Bridge + Log); add `quantanalyticsv1` locally if you use the analytics repo in the same tree. |
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
  quantanalyticsv1/    ← optional: CLI analytics on JSONL
```

**Steps**

1. Copy `orchestrator/config.example.env` → `orchestrator/.env` and set `QUANTBUILD_ROOT`, `QUANTBRIDGE_ROOT`, `QUANTLOG_ROOT`, and optionally **`QUANTANALYTICS_ROOT`** (see `config.vps.example.env`).
2. Install **`quantanalyticsv1`** editable into the QuantBuild venv when you use analytics: `pip install -e ../quantanalyticsv1`.
3. From `orchestrator/`:

   ```powershell
   python quantmetrics.py build -c configs/strict_prod_v2.yaml
   ```

   On Windows you can use `.\qm.ps1` if your wrapper forwards the same arguments.

4. Examples (see `python quantmetrics.py --help`):

   | Goal | Command |
   | --- | --- |
   | `quantbuildv1` live (paper; no `--real`) | `python quantmetrics.py build -c configs/strict_prod_v2.yaml` |
   | `quantbuildv1` backtest | `python quantmetrics.py backtest -c configs/foo.yaml` |
   | Backtest **then** JSONL analytics report | `python quantmetrics.py backtest -c configs/foo.yaml --analyze` |
   | Analytics only on a QuantLog `.jsonl` | `python quantmetrics.py analyze --jsonl path/to/run.jsonl` |
   | `quantbridgev1` mock regression suite | `python quantmetrics.py bridge regression` |

Use `python quantmetrics.py --help` and per-subcommand `--help` for full options.

**`quantbuildv1` + live bridge:** set `QUANTBRIDGE_SRC_PATH` to **`quantbridgev1`**’s `src` directory so build can load the bridge module — see [Suite start handout](docs/SUITE_START_HANDOUT.md).

---

## Requirements

- Python on the host (or per-repo venvs); override with `PYTHON` in `.env` if needed.
- Cloned **`quantbuildv1`**, **`quantbridgev1`**, and **`quantlogv1`** with paths in `.env` (clone **`quantanalyticsv1`** beside them when you run post-run JSONL reports).

---

## Documentation

- [GitHub profile README (template to paste)](docs/GITHUB_PROFILE_README.md) — landing page for `github.com/<you>/<you>`.
- [Suite showcase (technical CV)](docs/SHOWCASE.md) — problem, architecture rationale, validation, deployment roadmap.
- [Suite start (handout)](docs/SUITE_START_HANDOUT.md) — `.env`, common commands, workspace, `QUANTBRIDGE_SRC_PATH`.
- [Roadmap](docs/Roadmap_os.md)
- [Sprint plan](docs/QUANTMETRICS_SPRINT_PLAN.md)
