# PROMOTION DECISION

## Decision

- Run ID: qb_run_20260425T050607Z_d3b45081
- Promotion decision: VALIDATION_REQUIRED
- All rules passed: False
- Generated (UTC): 2026-04-25T05:09:50.507795Z

## Metrics Used

- Total trades: 45
- Expectancy R: 0.4000000000000027
- Profit factor: 1.750000000000005
- Input edge verdict: VALIDATION_REQUIRED
- Input confidence: LOW
- Major warning count: 1

## Rule Checks

| Rule | Passed | Fail outcome | Reason |
|---|---|---|---|
| confidence must not be LOW | False | VALIDATION_REQUIRED | confidence=LOW |
| total_trades must be >= 100 | False | VALIDATION_REQUIRED | total_trades=45 |
| expectancy_R must be > 0 | True | REJECT | expectancy_R=0.4000000000000027 |
| profit_factor must be >= 1.25 | True | REJECT | profit_factor=1.750000000000005 |
| at least one protective guard required | True | VALIDATION_REQUIRED | protective_guard_detected=True |
| major warnings must be absent | False | VALIDATION_REQUIRED | major_warnings=1 |

## Reasons

- confidence must not be LOW: confidence=LOW
- total_trades must be >= 100: total_trades=45
- major warnings must be absent: major_warnings=1

## Input Artifacts

- C:\Users\Gebruiker\quantmetrics-suite\quantmetrics_os\runs\EXP-2025-5year\single\analytics\edge_verdict.json
- C:\Users\Gebruiker\quantmetrics-suite\quantmetrics_os\runs\EXP-2025-5year\single\analytics\guard_attribution.json
- C:\Users\Gebruiker\quantmetrics-suite\quantmetrics_os\runs\EXP-2025-5year\single\analytics\edge_stability.json
- C:\Users\Gebruiker\quantmetrics-suite\quantmetrics_os\runs\EXP-2025-5year\single\analytics\decision_quality.csv
- C:\Users\Gebruiker\quantmetrics-suite\quantmetrics_os\runs\EXP-2025-5year\single\analytics\warnings.json
