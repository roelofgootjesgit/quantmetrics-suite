# Mentor Update - 5Y Promotion Gate

## Scope Completed

For run `qb_run_20260425T050607Z_d3b45081`, we completed:

- 5-year backtest execution
- canonical artifact bundling in `quantmetrics_os/runs/EXP-2025-5year/single`
- guard attribution analysis
- hard promotion gate decision

## Current Decision

- `edge_verdict`: `VALIDATION_REQUIRED`
- `promotion_decision`: `VALIDATION_REQUIRED`

## Why Promotion Is Blocked

Hard rules currently failing:

- confidence is `LOW`
- total trades is `45` (rule requires `>= 100`)
- major warnings count is `1`

## What Passed

- expectancy R is positive (`0.40`)
- profit factor is above threshold (`1.75 >= 1.25`)
- at least one protective guard was detected

## Conclusion

The gate behaves as designed: no promotion under weak sample evidence, even when some performance metrics look promising.

## Next Action In Progress

We are now expanding historical coverage and re-running the same pipeline to increase sample size and re-evaluate promotion eligibility under the same hard rules.

## Update After Expansion

Historical market cache was expanded (Dukascopy fetch) and the run was re-executed.

- Updated run: `qb_run_20260425T051333Z_7e01f5fe`
- Canonical bundle: `quantmetrics_os/runs/EXP-2025-5year-expanded/single`
- Trades increased: `45 -> 58`
- Promotion decision: `VALIDATION_REQUIRED`

### Remaining blockers

- confidence remains `LOW`
- total trades still below hard threshold (`58 < 100`)
- major warnings remain present (`1`)

### Positive checks still passing

- expectancy remains positive (`0.2931`)
- profit factor remains above threshold (`1.5151`)
- protective guard detected (`true`)

