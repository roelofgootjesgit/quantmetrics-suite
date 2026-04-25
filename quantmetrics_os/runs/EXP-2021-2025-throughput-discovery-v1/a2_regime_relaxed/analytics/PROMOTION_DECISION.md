# PROMOTION DECISION

## Decision

- Run ID: qb_run_20260425T053907Z_61305cdc
- Promotion decision: VALIDATION_REQUIRED
- All rules passed: False
- Generated (UTC): 2026-04-25T05:39:18.527831Z

## Metrics Used

- Total trades: 58
- Expectancy R: 0.2931034482758685
- Profit factor: 1.5151515151515265
- Max drawdown R (stability peak): 10.99999999999983
- Baseline max drawdown R: 10.99999999999983
- Input edge verdict: VALIDATION_REQUIRED
- Input confidence: LOW
- Major warning count: 1

## Rule Checks

| Rule | Passed | Fail outcome | Reason |
|---|---|---|---|
| confidence must not be LOW | False | VALIDATION_REQUIRED | confidence=LOW |
| total_trades must be >= 100 | False | VALIDATION_REQUIRED | total_trades=58 |
| expectancy_R must be > 0 | True | REJECT | expectancy_R=0.2931034482758685 |
| profit_factor must be >= 1.25 | True | REJECT | profit_factor=1.5151515151515265 |
| at least one protective guard required | True | VALIDATION_REQUIRED | protective_guard_detected=True |
| major warnings must be absent | False | VALIDATION_REQUIRED | major_warnings=1 |
| max_drawdown_R must not worsen materially vs baseline | True | VALIDATION_REQUIRED | max_dd_r=10.99999999999983, baseline_max_dd_r=10.99999999999983, threshold=13.200000 (ratio=1.2) |

## Reasons

- confidence must not be LOW: confidence=LOW
- total_trades must be >= 100: total_trades=58
- major warnings must be absent: major_warnings=1

## Input Artifacts

- C:\Users\Gebruiker\quantmetrics-suite\quantmetrics_os\runs\EXP-2021-2025-throughput-discovery-v1\a2_regime_relaxed\analytics\edge_verdict.json
- C:\Users\Gebruiker\quantmetrics-suite\quantmetrics_os\runs\EXP-2021-2025-throughput-discovery-v1\a2_regime_relaxed\analytics\guard_attribution.json
- C:\Users\Gebruiker\quantmetrics-suite\quantmetrics_os\runs\EXP-2021-2025-throughput-discovery-v1\a2_regime_relaxed\analytics\edge_stability.json
- C:\Users\Gebruiker\quantmetrics-suite\quantmetrics_os\runs\EXP-2021-2025-throughput-discovery-v1\a2_regime_relaxed\analytics\decision_quality.csv
- C:\Users\Gebruiker\quantmetrics-suite\quantmetrics_os\runs\EXP-2021-2025-throughput-discovery-v1\a2_regime_relaxed\analytics\warnings.json
