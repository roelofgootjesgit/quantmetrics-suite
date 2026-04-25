# EDGE REPORT

## 1. Run Summary

- Run ID: qb_run_20260425T051333Z_7e01f5fe
- Source events: C:\Users\Gebruiker\quantmetrics-suite\quantmetrics_os\runs\EXP-2025-5year-expanded\single\quantlog_events.jsonl
- Total events: 1009
- Total decision cycles: 167
- Completed cycles: 167
- Incomplete cycles: 0
- Output path: C:\Users\Gebruiker\quantmetrics-suite\quantmetrics_os\runs\EXP-2025-5year-expanded\single\analytics

## 2. Performance Summary

- Total trades: 58
- Expectancy R: 0.2931
- Win rate: 0.4310
- Profit factor: 1.5152
- Max drawdown R: 11.0000

## 3. Throughput Funnel (Diagnostics)

- raw_signals_detected: 167
- signals_after_filters: 58
- signals_executed: 58
- filter_kill_ratio: 0.6527
- execution_ratio: 0.3473
- trades_per_month: 3.0526

### Top guard blocks (events)

| Guard | Blocks |
|---|---:|
| regime_allowed_sessions | 55 |
| max_trades_per_session | 24 |
| regime_profile | 15 |
| daily_loss_cap | 14 |
| equity_drawdown_kill_switch | 1 |

### Top filter reasons (signal_filtered)

| Reason | Count |
|---|---:|
| session_blocked | 55 |
| position_limit_reached | 24 |
| regime_blocked | 15 |
| risk_blocked | 15 |

### Regime × guard blocks (top)

| Regime | Guard | Blocks |
|---|---|---:|
| trend | regime_allowed_sessions | 46 |
| trend | max_trades_per_session | 20 |
| compression | regime_profile | 15 |
| trend | daily_loss_cap | 14 |
| expansion | regime_allowed_sessions | 9 |
| expansion | max_trades_per_session | 4 |
| trend | equity_drawdown_kill_switch | 1 |

### Session × guard blocks (top)

| Session | Guard | Blocks |
|---|---|---:|
| Asia | regime_allowed_sessions | 55 |
| Asia | regime_profile | 15 |
| Overlap | max_trades_per_session | 10 |
| New York | daily_loss_cap | 10 |
| New York | max_trades_per_session | 8 |
| London | max_trades_per_session | 6 |
| Overlap | daily_loss_cap | 4 |
| New York | equity_drawdown_kill_switch | 1 |

## 4. Guard Attribution

| Guard | Blocks | Allows | Trades | Expectancy R | PF | Verdict |
|---|---:|---:|---:|---:|---:|---|
| backtest_pipeline | 0 | 0 | 58 | 0.2931 | 1.5152 | EDGE_PROTECTIVE |
| daily_loss_cap | 0 | 0 | 0 | n/a | n/a | INSUFFICIENT_DATA |
| equity_drawdown_kill_switch | 0 | 0 | 0 | n/a | n/a | INSUFFICIENT_DATA |
| max_trades_per_session | 0 | 0 | 0 | n/a | n/a | UNKNOWN |
| regime_allowed_sessions | 0 | 0 | 0 | n/a | n/a | UNKNOWN |
| regime_profile | 0 | 0 | 0 | n/a | n/a | INSUFFICIENT_DATA |

## 5. Regime Breakdown

| Regime | Trades | Expectancy R | PF | Sample | Verdict |
|---|---:|---:|---:|---|---|
| compression | 0 | n/a | n/a | INSUFFICIENT_DATA | UNSTABLE |
| expansion | 15 | 0.4000 | 1.7500 | INSUFFICIENT_DATA | PROMISING_BUT_WEAK |
| trend | 43 | 0.2558 | 1.4400 | WEAK_EVIDENCE | PROMISING_BUT_WEAK |

## 6. Session Breakdown

| Session | Trades | Expectancy R | PF | Sample | Verdict |
|---|---:|---:|---:|---|---|
| Asia | 0 | n/a | n/a | INSUFFICIENT_DATA | UNSTABLE |
| London | 9 | 0.3333 | 1.6000 | INSUFFICIENT_DATA | PROMISING_BUT_WEAK |
| New York | 22 | 0.2273 | 1.3846 | WEAK_EVIDENCE | PROMISING_BUT_WEAK |
| Overlap | 27 | 0.3333 | 1.6000 | WEAK_EVIDENCE | PROMISING_BUT_WEAK |

## 7. Decision Quality

- High quality cycles: 25
- Medium quality cycles: 0
- Low quality cycles: 33
- Unknown cycles: 109

## 8. Warnings

- UNKNOWN_DECISION_QUALITY: {'code': 'UNKNOWN_DECISION_QUALITY', 'count': 109}

## 9. Final Verdict

- Edge verdict: VALIDATION_REQUIRED
- Confidence: LOW
- Main strength: 1 guard(s) show protective behavior
- Main risk: Sample size too small to justify promotion
- Recommended next action: Increase representative sample size before production changes
