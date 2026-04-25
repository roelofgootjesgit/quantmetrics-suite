# quantmetrics_os

## SYSTEM IDENTITY

This module is part of the QuantMetrics suite.
- Canonical name: `quantmetrics_os` (alias: QuantOS)
- Role: Orchestration Layer

`quantmetrics_os` is the front door of the suite: one place to resolve paths, environment, and subprocess entry points for `quantbuild`, `quantbridge`, `quantlog`, and `quantanalytics`.

---

## Core responsibility

- Resolve sibling repository roots and runtime environment.
- Provide one CLI entry for build, backtest, bridge checks, and analytics.
- Keep orchestration concerns separate from strategy, execution, and logging code.
- Collect reproducible run artifacts under `runs/`.

## Correlation with the total system

`quantmetrics_os` is the orchestration and artifact correlation hub:

- binds one run context to concrete artifact paths under `runs/<experiment>/<role>/`
- keeps config snapshots aligned with produced `quantlog_events.jsonl` and analytics outputs
- enables baseline-vs-candidate comparison outputs under `runs/<experiment>/comparisons/...`

Operationally, it correlates module outputs by run lineage:
`quantbuild` decisions -> `quantbridge` execution -> `quantlog` events -> `quantanalytics` diagnostics -> `quantresearch` decisions.

---

## Repository layout

| Path | Purpose |
| --- | --- |
| `orchestrator/quantmetrics.py` | Main orchestrator CLI and subprocess launcher. |
| `orchestrator/qm.ps1` | Windows wrapper for orchestrator commands. |
| `orchestrator/config.example.env` | Baseline environment template for suite paths. |
| `orchestrator/config.vps.example.env` | VPS/Linux path and env template. |
| `scripts/clone_quant_suite.sh` | Clone/update helper for suite repos. |
| `vscode/quant-suite.code-workspace` | Multi-root workspace for suite development. |
| `docs/` | Handouts, roadmap, and implementation documentation. |
| `runs/` | Collected experiment artifacts and analytics bundles. |

Run artifact convention:
- `config_snapshot.yaml`: input `--config` file copy.
- `resolved_config.yaml`: merged effective config (redacted secrets).
- `quantlog_events.jsonl`, `run_info.json`, and optional `analytics/`.
- cross-run compare artifacts under `runs/<experiment>/comparisons/<comparison_id>/`.

### Cross-run comparison artifacts

```text
quantmetrics_os/runs/<experiment>/
  <role>/...
  comparisons/
    baseline_vs_candidate_001/
      comparison_report.md
      metrics.json
```

Build them with:

```powershell
python scripts/compare_runs.py `
  --baseline-jsonl runs/<experiment>/baseline/quantlog_events.jsonl `
  --candidate-jsonl runs/<experiment>/candidate/quantlog_events.jsonl `
  --output-dir runs/<experiment>/comparisons/baseline_vs_candidate_001
```

---

## Quick start

Expected folder layout:

```text
<parent>/
  quantmetrics_os/
  quantbuild/
  quantbridge/
  quantlog/
  quantanalytics/   (optional but recommended for reports)
```

1. Copy `orchestrator/config.example.env` to `orchestrator/.env`.
2. Set `QUANTBUILD_ROOT`, `QUANTBRIDGE_ROOT`, `QUANTLOG_ROOT` and optional `QUANTANALYTICS_ROOT`.
3. Run from `orchestrator/`:

```powershell
python quantmetrics.py build -c configs/strict_prod_v2.yaml
```

Useful commands:

```powershell
python quantmetrics.py backtest -c configs/foo.yaml
python quantmetrics.py backtest -c configs/foo.yaml --analyze
python quantmetrics.py analyze --jsonl path/to/run.jsonl
python quantmetrics.py bridge regression
```

---

## Documentation

- [docs/SUITE_START_HANDOUT.md](docs/SUITE_START_HANDOUT.md)
- [docs/RUN_ARTIFACT_STRATEGY.md](docs/RUN_ARTIFACT_STRATEGY.md)
- [docs/SHOWCASE.md](docs/SHOWCASE.md)
- [docs/QUANTMETRICS_SPRINT_PLAN.md](docs/QUANTMETRICS_SPRINT_PLAN.md)
- [docs/Roadmap_os.md](docs/Roadmap_os.md)

---

## Suite repositories (GitHub)

| Repo | Remote |
| --- | --- |
| `quantmetrics_os` (**this**) | [roelofgootjesgit/quantmetrics_os](https://github.com/roelofgootjesgit/quantmetrics_os) |
| `quantbuild` | [roelofgootjesgit/QuantBuild-Signal-Engine](https://github.com/roelofgootjesgit/QuantBuild-Signal-Engine) |
| `quantbridge` | canonical module: `quantbridge` |
| `quantlog` | canonical module: `quantlog` |
| `quantanalytics` | canonical module: `quantanalytics` |
