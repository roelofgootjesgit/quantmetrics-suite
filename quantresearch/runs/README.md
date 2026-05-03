# (Optioneel) Duplicaat-bundels

**Canonieke run-output voor het team:** `quantmetrics_os/runs/<experiment_id>/` via QuantBuild `artifacts.enabled` (zie `quantbuild/docs/STRATEGY_SYSTEM_OVERVIEW.md`).

Deze map kan worden gevuld met een **extra** kopie (`quantresearch_runs.enabled` in QuantBuild) — standaard niet nodig.

## HYP-002 pipeline-bundels

Na `python -m quantresearch hyp002-pipeline` (of `quantresearch-hyp002-pipeline`) verschijnt hier o.a.:

`runs/hyp002-v5a-expansion-block-closed-2026/metrics_bundle.json`

— samengevatte `expectancy_r` / `trade_count` per geconfigureerde QuantBuild-run, plus `experiments.json`-update (**EXP-002**). Zie `pipelines/hyp002_promotion_bundle.json`.
