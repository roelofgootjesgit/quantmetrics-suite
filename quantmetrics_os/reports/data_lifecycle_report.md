# Data Lifecycle Report (V0 Dry Run)

- Generated (UTC): `2026-04-25T07:01:46.504269Z`
- Runs scanned: `15`
- Unknown status runs: `15`
- Total size: `11.53 MB` (12094001 bytes)
- Actions: `none` (V0 does not delete/compress/mutate)

## Run table

| Experiment | Role | Run ID | Status | Delete allowed | Size | Path | Notes |
|---|---|---|---|---|---:|---|---|
| EXP-2021-2025-session-relax-watchlist-v1 | b0_baseline | qb_run_20260425T055434Z_78f6ef7c | unknown | False | 933.12 KB | `runs/EXP-2021-2025-session-relax-watchlist-v1/b0_baseline` | missing status.json; manual classification required |
| EXP-2021-2025-session-relax-watchlist-v1 | b1_london_only_relaxed | qb_run_20260425T055454Z_3f78ff9c | unknown | False | 933.69 KB | `runs/EXP-2021-2025-session-relax-watchlist-v1/b1_london_only_relaxed` | missing status.json; manual classification required |
| EXP-2021-2025-session-relax-watchlist-v1 | b2_ny_only_relaxed | qb_run_20260425T055514Z_7a7f7a73 | unknown | False | 921.61 KB | `runs/EXP-2021-2025-session-relax-watchlist-v1/b2_ny_only_relaxed` | missing status.json; manual classification required |
| EXP-2021-2025-session-relax-watchlist-v1 | b3_overlap_relaxed | qb_run_20260425T055536Z_36979f52 | unknown | False | 933.65 KB | `runs/EXP-2021-2025-session-relax-watchlist-v1/b3_overlap_relaxed` | missing status.json; manual classification required |
| EXP-2021-2025-session-relax-watchlist-v1 | b4_full_session_relaxed | qb_run_20260425T055556Z_45ea944c | unknown | False | 741.42 KB | `runs/EXP-2021-2025-session-relax-watchlist-v1/b4_full_session_relaxed` | missing status.json; manual classification required |
| EXP-2021-2025-throughput-discovery-v1 | _generated_configs | - | unknown | False | 5.47 KB | `runs/EXP-2021-2025-throughput-discovery-v1/_generated_configs` | missing status.json; manual classification required |
| EXP-2021-2025-throughput-discovery-v1 | a0_baseline | qb_run_20260425T053826Z_7c56e609 | unknown | False | 933.10 KB | `runs/EXP-2021-2025-throughput-discovery-v1/a0_baseline` | missing status.json; manual classification required |
| EXP-2021-2025-throughput-discovery-v1 | a1_session_relaxed | qb_run_20260425T053850Z_4e551417 | unknown | False | 741.35 KB | `runs/EXP-2021-2025-throughput-discovery-v1/a1_session_relaxed` | missing status.json; manual classification required |
| EXP-2021-2025-throughput-discovery-v1 | a2_regime_relaxed | qb_run_20260425T053907Z_61305cdc | unknown | False | 934.66 KB | `runs/EXP-2021-2025-throughput-discovery-v1/a2_regime_relaxed` | missing status.json; manual classification required |
| EXP-2021-2025-throughput-discovery-v1 | a3_cooldown_relaxed | qb_run_20260425T053925Z_5fe05f75 | unknown | False | 935.29 KB | `runs/EXP-2021-2025-throughput-discovery-v1/a3_cooldown_relaxed` | missing status.json; manual classification required |
| EXP-2021-2025-throughput-discovery-v1 | a4_session_regime_relaxed | qb_run_20260425T053950Z_656da8a9 | unknown | False | 741.88 KB | `runs/EXP-2021-2025-throughput-discovery-v1/a4_session_regime_relaxed` | missing status.json; manual classification required |
| EXP-2021-2025-throughput-discovery-v1 | a5_throughput_discovery | qb_run_20260425T054010Z_1a326ba3 | unknown | False | 744.28 KB | `runs/EXP-2021-2025-throughput-discovery-v1/a5_throughput_discovery` | missing status.json; manual classification required |
| EXP-2025-5year | single | qb_run_20260425T050607Z_d3b45081 | unknown | False | 987.82 KB | `runs/EXP-2025-5year/single` | missing status.json; manual classification required |
| EXP-2025-5year-expanded | single | qb_run_20260425T051333Z_7e01f5fe | unknown | False | 932.75 KB | `runs/EXP-2025-5year-expanded/single` | missing status.json; manual classification required |
| EXP-2025-baseline | single | qb_run_20260425T042136Z_dbd1b0cc | unknown | False | 390.47 KB | `runs/EXP-2025-baseline/single` | missing status.json; manual classification required |

## Guardrails (enforced in V0)

- No deletion
- No compression
- No archive writes
- No status mutation (missing `status.json` is reported as `unknown` only)
