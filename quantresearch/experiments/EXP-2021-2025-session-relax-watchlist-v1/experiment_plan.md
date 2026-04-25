# Experiment plan

## QuantOS

Matrix preset: **`session-relax-watchlist`** (`throughput_discovery_matrix.py --matrix session-relax-watchlist`).

Generated configs: `quantbuild/configs/_throughput_discovery/<experiment_id>/B*.yaml`

Artifacts: `quantmetrics_os/runs/<experiment_id>/b*_*/` plus `THROUGHPUT_DISCOVERY_SUMMARY.md`, `throughput_discovery_registry.json`, `THROUGHPUT_COMPARE.{json,md}` (compare baseline defaults to **`b0_baseline`**).

Example:

```text
python quantmetrics_os/scripts/throughput_discovery_matrix.py ^
  --matrix session-relax-watchlist ^
  --experiment-id EXP-2021-2025-session-relax-watchlist-v1 ^
  --base-config configs/strict_prod_v2.yaml ^
  --start-date 2021-01-01 ^
  --end-date 2025-12-31
```

Or via orchestrator (subcommand name is still `throughput-discovery`; it forwards to the same script):

`python quantmetrics_os/orchestrator/quantmetrics.py experiments throughput-discovery --matrix session-relax-watchlist --experiment-id EXP-2021-2025-session-relax-watchlist-v1 -c configs/strict_prod_v2.yaml --start-date 2021-01-01 --end-date 2025-12-31`

## Variant intent (implementation mapping)

| Variant | Intent |
| --- | --- |
| B0 | Baseline control |
| B1 | Expansion `allowed_sessions` includes **London** (was NY+Overlap only in strict_prod_v2) |
| B2 | Expansion **New York only**; `min_hour_utc` set to **0** (relax NY window gate) |
| B3 | Expansion **New York + Overlap**; `min_hour_utc` **0** (relax overlap timing vs baseline 10) |
| B4 | `filters.session: false` — broadest session-side relax in this matrix |

Hard risk parameters in YAML (daily loss, equity kill, position limits, etc.) are **not** targets for relaxation in this plan.
