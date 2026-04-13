# QuantOS Orchestrator

Single entrypoint for a decoupled multi-repo trading infrastructure stack.

QuantOS solves one problem: three independent repositories (strategy engine, 
broker execution, observability) need to run as one system without coupling 
their codebases together. This orchestrator handles environment resolution, 
path wiring, and subprocess lifecycle — so each component stays independently 
deployable and testable.

---

## The problem it solves

Running a multi-repo system without an orchestration layer means:
- Manual path management across repos
- Environment variables duplicated or mismatched per component
- No single command to verify the full stack is wired correctly
- Post-run analysis triggered manually, inconsistently

QuantOS eliminates all of that.

---

## How it works
orchestrator/.env
│
▼
quantmetrics.py
│
├── resolves QUANTBUILD_ROOT, QUANTBRIDGE_ROOT, QUANTLOG_ROOT
├── validates paths exist before launching anything
├── sets PYTHONPATH per subprocess so imports resolve correctly
│
├──▶ subprocess: python -m src.quantbuild.app   (QuantBuild)
├──▶ subprocess: python scripts/ctrader_smoke.py (QuantBridge)
└──▶ subprocess: python -m quantlog.cli          (QuantLog)

Each component runs in its own process with its own working directory.
No shared state. No import coupling between repos.

---

## Design decisions

**Why subprocesses, not imports?**
Importing across repos requires either installing packages or manipulating 
sys.path globally. Subprocesses keep each repo fully independent — 
you can update, test, or replace any component without touching the others.

**Why a single .env in the orchestrator?**
Each repo has its own .env for component-specific secrets. The orchestrator 
.env only holds paths and cross-repo wiring — a clear separation between 
infrastructure config and application config.

**Why explicit path validation on startup?**
Fail loud, fail early. A misconfigured path surfaces immediately on 
`quantmetrics.py check` rather than halfway through a live session.

---

## What lives here

| Path | Role |
|------|------|
| `orchestrator/quantmetrics.py` | Core: env loading, path resolution, subprocess dispatch |
| `orchestrator/qm.ps1` | Windows wrapper |
| `orchestrator/config.example.env` | Template: `*_ROOT` paths, optional `PYTHON` override |
| `orchestrator/config.vps.example.env` | VPS / Linux path layout |
| `vscode/quant-suite.code-workspace` | Multi-root workspace for all four repos |
| `scripts/clone_quant_suite.sh` | Clone/update all suite repos + generate baseline `.env` |

---

## CLI reference
python quantmetrics.py check                          # validate all paths
python quantmetrics.py build -c configs/strict_prod_v2.yaml   # launch QuantBuild
python quantmetrics.py bridge smoke --mode mock       # QuantBridge smoke test
python quantmetrics.py log validate-events -- --path <day>    # QuantLog validation
python quantmetrics.py post-run YYYY-MM-DD            # validate + summarize + score

On Windows: replace `python quantmetrics.py` with `.\qm.ps1`

---

## Suite components

| Repo | Role |
|------|------|
| [QuantBuild E1](https://github.com/roelofgootjesgit/quantbuildE1) | Strategy engine — regime detection, risk, portfolio heat |
| [QuantBridge](https://github.com/roelofgootjesgit/quantBridge-v.1) | Execution — broker-agnostic adapter, cTrader OpenAPI, multi-account routing |
| [QuantLog](https://github.com/roelofgootjesgit/quantlog-v.1) | Observability — JSONL event store, schema validation, trace replay |

---

## Requirements

- Python on host (override binary with `PYTHON` in `.env`)
- Three sibling repos cloned and paths set in `orchestrator/.env`

Recommended layout:
<parent>/
QuantOS-Orchestrator/
quantbuildv1/
quantbridgev1/
quantlogv1/
