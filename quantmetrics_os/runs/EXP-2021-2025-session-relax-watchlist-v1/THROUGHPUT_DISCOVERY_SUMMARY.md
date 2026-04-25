# SESSION RELAX WATCHLIST SUMMARY

*Generated (UTC): 2026-04-25T05:56:08.221457Z*

## Matrix

- experiment_id: `EXP-2021-2025-session-relax-watchlist-v1`
- base_config: `C:\Users\Gebruiker\quantmetrics-suite\quantbuild\configs\strict_prod_v2.yaml`
- window: `2021-01-01` .. `2025-12-31`

| Experiment | run_id | raw | after_filters | executed | kill_ratio | exec_ratio | trades | expectancy_R | PF | max_dd_R | promotion |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| B0_BASELINE | `qb_run_20260425T055434Z_78f6ef7c` | 167 | 58 | 58 | 0.6527 | 0.3473 | 58 | 0.2931 | 1.5152 | 11.0000 | VALIDATION_REQUIRED |
| B1_LONDON_ONLY_RELAXED | `qb_run_20260425T055454Z_3f78ff9c` | 167 | 58 | 58 | 0.6527 | 0.3473 | 58 | 0.2931 | 1.5152 | 11.0000 | VALIDATION_REQUIRED |
| B2_NY_ONLY_RELAXED | `qb_run_20260425T055514Z_7a7f7a73` | 166 | 55 | 55 | 0.6687 | 0.3313 | 55 | 0.2545 | 1.4375 | 11.0000 | VALIDATION_REQUIRED |
| B3_OVERLAP_RELAXED | `qb_run_20260425T055536Z_36979f52` | 167 | 58 | 58 | 0.6527 | 0.3473 | 58 | 0.2931 | 1.5152 | 11.0000 | VALIDATION_REQUIRED |
| B4_FULL_SESSION_RELAXED | `qb_run_20260425T055556Z_45ea944c` | 122 | 63 | 63 | 0.4836 | 0.5164 | 63 | 0.4286 | 1.8182 | 10.0000 | VALIDATION_REQUIRED |

## Artifacts

Each variant is collected as its own role folder under:

- `C:\Users\Gebruiker\quantmetrics-suite\quantmetrics_os\runs\EXP-2021-2025-session-relax-watchlist-v1/<ROLE>/`

Each role folder should contain:

- `analytics/throughput.json`
- `analytics/guard_attribution.json`
- `analytics/edge_verdict.json`
- `analytics/promotion_decision.json`
- `analytics/EDGE_REPORT.md`

