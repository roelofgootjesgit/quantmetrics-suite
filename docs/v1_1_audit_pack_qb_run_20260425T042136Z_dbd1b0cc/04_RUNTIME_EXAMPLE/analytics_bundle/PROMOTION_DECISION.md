# PROMOTION DECISION

## Decision

- Run ID: qb_run_20260425T042136Z_dbd1b0cc
- Promotion decision: REJECT
- All rules passed: False
- Generated (UTC): 2026-04-25T05:04:33.029664Z

## Metrics Used

- Total trades: 11
- Expectancy R: -0.7272727272727273
- Profit factor: 0.2
- Input edge verdict: VALIDATION_REQUIRED
- Input confidence: LOW
- Major warning count: 1

## Rule Checks

| Rule | Passed | Fail outcome | Reason |
|---|---|---|---|
| confidence must not be LOW | False | VALIDATION_REQUIRED | confidence=LOW |
| total_trades must be >= 100 | False | VALIDATION_REQUIRED | total_trades=11 |
| expectancy_R must be > 0 | False | REJECT | expectancy_R=-0.7272727272727273 |
| profit_factor must be >= 1.25 | False | REJECT | profit_factor=0.2 |
| at least one protective guard required | False | VALIDATION_REQUIRED | protective_guard_detected=False |
| major warnings must be absent | False | VALIDATION_REQUIRED | major_warnings=1 |

## Reasons

- expectancy_R must be > 0: expectancy_R=-0.7272727272727273
- profit_factor must be >= 1.25: profit_factor=0.2
- confidence must not be LOW: confidence=LOW
- total_trades must be >= 100: total_trades=11
- at least one protective guard required: protective_guard_detected=False
- major warnings must be absent: major_warnings=1

## Input Artifacts

- C:\Users\Gebruiker\quantmetrics-suite\quantmetrics_os\runs\EXP-2025-baseline\single\analytics\edge_verdict.json
- C:\Users\Gebruiker\quantmetrics-suite\quantmetrics_os\runs\EXP-2025-baseline\single\analytics\guard_attribution.json
- C:\Users\Gebruiker\quantmetrics-suite\quantmetrics_os\runs\EXP-2025-baseline\single\analytics\edge_stability.json
- C:\Users\Gebruiker\quantmetrics-suite\quantmetrics_os\runs\EXP-2025-baseline\single\analytics\decision_quality.csv
- C:\Users\Gebruiker\quantmetrics-suite\quantmetrics_os\runs\EXP-2025-baseline\single\analytics\warnings.json
