# EDGE REPORT

## 1. Run Summary

- Run ID: qb_run_20260425T050607Z_d3b45081
- Source events: C:\Users\Gebruiker\quantmetrics-suite\quantmetrics_os\runs\EXP-2025-5year\single\quantlog_events.jsonl
- Total events: 1075
- Total decision cycles: 188
- Completed cycles: 188
- Incomplete cycles: 0
- Output path: C:\Users\Gebruiker\quantmetrics-suite\quantmetrics_os\runs\EXP-2025-5year\single\analytics

## 2. Performance Summary

- Total trades: 45
- Expectancy R: 0.4000
- Win rate: 0.4667
- Profit factor: 1.7500
- Max drawdown R: 9.0000

## 3. Guard Attribution

| Guard | Blocks | Allows | Trades | Expectancy R | PF | Verdict |
|---|---:|---:|---:|---:|---:|---|
| backtest_pipeline | 0 | 0 | 45 | 0.4000 | 1.7500 | EDGE_PROTECTIVE |
| daily_loss_cap | 0 | 0 | 0 | n/a | n/a | INSUFFICIENT_DATA |
| max_trades_per_session | 0 | 0 | 0 | n/a | n/a | INSUFFICIENT_DATA |
| regime_allowed_sessions | 0 | 0 | 0 | n/a | n/a | UNKNOWN |
| regime_profile | 0 | 0 | 0 | n/a | n/a | INSUFFICIENT_DATA |

## 4. Regime Breakdown

| Regime | Trades | Expectancy R | PF | Sample | Verdict |
|---|---:|---:|---:|---|---|
| compression | 0 | n/a | n/a | INSUFFICIENT_DATA | UNSTABLE |
| expansion | 6 | 1.5000 | 10.0000 | INSUFFICIENT_DATA | PROMISING_BUT_WEAK |
| trend | 39 | 0.2308 | 1.3913 | WEAK_EVIDENCE | PROMISING_BUT_WEAK |

## 5. Session Breakdown

| Session | Trades | Expectancy R | PF | Sample | Verdict |
|---|---:|---:|---:|---|---|
| Asia | 0 | n/a | n/a | INSUFFICIENT_DATA | UNSTABLE |
| London | 6 | -0.5000 | 0.4000 | INSUFFICIENT_DATA | WEAK_OR_NEGATIVE |
| New York | 29 | 0.7586 | 2.8333 | WEAK_EVIDENCE | PROMISING_BUT_WEAK |
| Overlap | 10 | -0.1000 | 0.8571 | INSUFFICIENT_DATA | WEAK_OR_NEGATIVE |

## 6. Decision Quality

- High quality cycles: 21
- Medium quality cycles: 0
- Low quality cycles: 24
- Unknown cycles: 143

## 7. Warnings

- UNKNOWN_DECISION_QUALITY: {'code': 'UNKNOWN_DECISION_QUALITY', 'count': 143}

## 8. Final Verdict

- Edge verdict: VALIDATION_REQUIRED
- Confidence: LOW
- Main strength: 1 guard(s) show protective behavior
- Main risk: Sample size too small to justify promotion
- Recommended next action: Increase representative sample size before production changes
