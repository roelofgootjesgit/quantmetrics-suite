# EDGE REPORT

## 1. Run Summary

- Run ID: qb_run_20260425T042136Z_dbd1b0cc
- Source events: C:\Users\Gebruiker\quantmetrics-suite\quantmetrics_os\runs\EXP-2025-baseline\single\quantlog_events.jsonl
- Total events: 408
- Total decision cycles: 75
- Completed cycles: 75
- Incomplete cycles: 0
- Output path: C:\Users\Gebruiker\quantmetrics-suite\quantmetrics_os\runs\EXP-2025-baseline\single\analytics

## 2. Performance Summary

- Total trades: 11
- Expectancy R: -0.7273
- Win rate: 0.0909
- Profit factor: 0.2000
- Max drawdown R: 10.0000

## 3. Guard Attribution

| Guard | Blocks | Allows | Trades | Expectancy R | PF | Verdict |
|---|---:|---:|---:|---:|---:|---|
| backtest_pipeline | 0 | 0 | 11 | -0.7273 | 0.2000 | INSUFFICIENT_DATA |
| daily_loss_cap | 0 | 0 | 0 | n/a | n/a | INSUFFICIENT_DATA |
| equity_drawdown_kill_switch | 0 | 0 | 0 | n/a | n/a | INSUFFICIENT_DATA |
| regime_allowed_sessions | 0 | 0 | 0 | n/a | n/a | UNKNOWN |
| regime_profile | 0 | 0 | 0 | n/a | n/a | INSUFFICIENT_DATA |

## 4. Regime Breakdown

| Regime | Trades | Expectancy R | PF | Sample | Verdict |
|---|---:|---:|---:|---|---|
| compression | 0 | n/a | n/a | INSUFFICIENT_DATA | UNSTABLE |
| expansion | 0 | n/a | n/a | INSUFFICIENT_DATA | UNSTABLE |
| trend | 11 | -0.7273 | 0.2000 | INSUFFICIENT_DATA | WEAK_OR_NEGATIVE |

## 5. Session Breakdown

| Session | Trades | Expectancy R | PF | Sample | Verdict |
|---|---:|---:|---:|---|---|
| Asia | 0 | n/a | n/a | INSUFFICIENT_DATA | UNSTABLE |
| London | 3 | -1.0000 | 0.0000 | INSUFFICIENT_DATA | WEAK_OR_NEGATIVE |
| New York | 6 | -0.5000 | 0.4000 | INSUFFICIENT_DATA | WEAK_OR_NEGATIVE |
| Overlap | 2 | -1.0000 | 0.0000 | INSUFFICIENT_DATA | WEAK_OR_NEGATIVE |

## 6. Decision Quality

- High quality cycles: 1
- Medium quality cycles: 0
- Low quality cycles: 10
- Unknown cycles: 64

## 7. Warnings

- UNKNOWN_DECISION_QUALITY: {'code': 'UNKNOWN_DECISION_QUALITY', 'count': 64}

## 8. Final Verdict

- Edge verdict: VALIDATION_REQUIRED
- Confidence: LOW
- Main strength: No clearly protective guard detected
- Main risk: Sample size too small to justify promotion
- Recommended next action: Increase representative sample size before production changes
