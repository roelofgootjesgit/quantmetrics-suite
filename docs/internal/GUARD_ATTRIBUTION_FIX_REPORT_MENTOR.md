# Mentor Report - Guard Attribution Engine v1 Fix

## Status

The Guard Attribution Engine v1 has been implemented in `quantanalytics` and validated with tests and a real run artifact.

- Build status: complete
- Test status: pass (`9/9`)
- Runtime status: pass (CLI executed successfully)
- Output status: all required analytics files written to canonical run output path

## What Was Fixed

Implemented a new analysis-only module at:

- `quantanalytics/src/quantanalytics/guard_attribution/`

With the required components:

- `loader.py` (JSONL loading, hard-fail invalid JSON, event counts, core-field warnings)
- `models.py` (`DecisionCycle` dataclass model)
- `decision_cycles.py` (cycle reconstruction + lifecycle warnings)
- `attribution.py` (guard attribution metrics + verdict logic + counterfactual handling)
- `scoring.py` (decision quality scoring + labels + warnings output)
- `stability.py` (symbol/regime/session/month/quarter/guard stability metrics)
- `verdict.py` (run-level edge verdict engine, low-sample protection)
- `report.py` (`EDGE_REPORT.md` generation)
- `cli.py` (end-to-end pipeline execution)

Also added:

- Compatibility runtime bridge under `quantanalytics/guard_attribution/` for module invocation
- Tests under `quantanalytics/tests/guard_attribution/`
- Packaging updates in `quantanalytics/pyproject.toml`

## Validation Evidence

### 1) Suite preflight

Executed:

- `python scripts/check_suite_layout.py` from `quantbuild`

Result:

- Pass (with `QUANTMETRICS_SUITE_ROOT` set to canonical root)

### 2) Unit/integration test slice

Executed:

- `pytest -q tests/guard_attribution`

Result:

- `9 passed`

### 3) Real run execution

Executed:

- `python -m quantanalytics.guard_attribution.cli --events "C:\Users\Gebruiker\quantmetrics-suite\quantmetrics_os\runs\EXP-2025-baseline\single\quantlog_events.jsonl" --run-id "qb_run_20260425T042136Z_dbd1b0cc" --out "C:\Users\Gebruiker\quantmetrics-suite\quantmetrics_os\runs\EXP-2025-baseline\single\analytics"`

Result:

- Success (exit code 0)

Generated files:

- `EDGE_REPORT.md`
- `guard_attribution.json`
- `decision_quality.csv`
- `edge_stability.json`
- `edge_verdict.json`
- `warnings.json`

## Current Run Outcome (Observed)

From `edge_verdict.json`:

- `edge_verdict`: `VALIDATION_REQUIRED`
- `confidence`: `LOW`
- `main_strength`: `No clearly protective guard detected`
- `main_risk`: `Sample size too small to justify promotion`

From `EDGE_REPORT.md`:

- Total events: `408`
- Total decision cycles: `75`
- Completed cycles: `75`
- Total trades: `11`
- Expectancy R: `-0.7273`
- Profit factor: `0.2000`

This behavior is aligned with the non-negotiable design rule:

- no overclaiming
- low sample and weak outcomes remain in validation-required state

## Risk & Boundary Compliance

Confirmed by implementation:

- Analysis-only behavior in `quantanalytics`
- No order placement/execution logic added
- No mutation of QuantLog event source files
- Warnings emitted when evidence is insufficient/unknown

## Recommendation

Proceed with additional run collection and guard-level sample expansion before any promotion decision.
