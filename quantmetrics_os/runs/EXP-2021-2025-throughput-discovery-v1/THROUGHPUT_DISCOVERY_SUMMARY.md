# THROUGHPUT DISCOVERY SUMMARY

*Generated (UTC): 2026-04-25T05:40:25.915438Z*

## Matrix

- experiment_id: `EXP-2021-2025-throughput-discovery-v1`
- base_config: `C:\Users\Gebruiker\quantmetrics-suite\quantbuild\configs\strict_prod_v2.yaml`
- window: `2021-01-01` .. `2025-12-31`

| Experiment | run_id | raw | after_filters | executed | kill_ratio | exec_ratio | trades | expectancy_R | PF | max_dd_R | promotion |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| A0_BASELINE | `qb_run_20260425T053826Z_7c56e609` | 167 | 58 | 58 | 0.6527 | 0.3473 | 58 | 0.2931 | 1.5152 | 11.0000 | VALIDATION_REQUIRED |
| A1_SESSION_RELAXED | `qb_run_20260425T053850Z_4e551417` | 122 | 63 | 63 | 0.4836 | 0.5164 | 63 | 0.4286 | 1.8182 | 10.0000 | VALIDATION_REQUIRED |
| A2_REGIME_RELAXED | `qb_run_20260425T053907Z_61305cdc` | 167 | 58 | 58 | 0.6527 | 0.3473 | 58 | 0.2931 | 1.5152 | 11.0000 | VALIDATION_REQUIRED |
| A3_COOLDOWN_RELAXED | `qb_run_20260425T053925Z_5fe05f75` | 167 | 58 | 58 | 0.6527 | 0.3473 | 58 | 0.2931 | 1.5152 | 11.0000 | VALIDATION_REQUIRED |
| A4_SESSION_REGIME_RELAXED | `qb_run_20260425T053950Z_656da8a9` | 122 | 63 | 63 | 0.4836 | 0.5164 | 63 | 0.4286 | 1.8182 | 10.0000 | VALIDATION_REQUIRED |
| A5_THROUGHPUT_DISCOVERY | `qb_run_20260425T054010Z_1a326ba3` | 122 | 63 | 63 | 0.4836 | 0.5164 | 63 | 0.4286 | 1.8182 | 10.0000 | VALIDATION_REQUIRED |

## Artifacts

Each variant is collected as its own role folder under:

- `C:\Users\Gebruiker\quantmetrics-suite\quantmetrics_os\runs\EXP-2021-2025-throughput-discovery-v1/<ROLE>/`

Each role folder should contain:

- `analytics/throughput.json`
- `analytics/guard_attribution.json`
- `analytics/edge_verdict.json`
- `analytics/promotion_decision.json`
- `analytics/EDGE_REPORT.md`

