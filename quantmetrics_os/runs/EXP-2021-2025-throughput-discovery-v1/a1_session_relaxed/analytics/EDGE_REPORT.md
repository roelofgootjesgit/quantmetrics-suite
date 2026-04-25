# EDGE REPORT

## 1. Run Summary

- Run ID: qb_run_20260425T053850Z_4e551417
- Source events: C:\Users\Gebruiker\quantmetrics-suite\quantbuild\data\quantlog_events\runs\qb_run_20260425T053850Z_4e551417.jsonl
- Total events: 799
- Total decision cycles: 122
- Completed cycles: 122
- Incomplete cycles: 0
- Output path: C:\Users\Gebruiker\quantmetrics-suite\quantmetrics_os\runs\EXP-2021-2025-throughput-discovery-v1\a1_session_relaxed\analytics

## 2. Performance Summary

- Total trades: 63
- Expectancy R: 0.4286
- Win rate: 0.4762
- Profit factor: 1.8182
- Max drawdown R: 8.0000

## 3. Throughput Funnel (Diagnostics)

- raw_signals_detected: 122
- signals_after_filters: 63
- signals_executed: 63
- filter_kill_ratio: 0.4836
- execution_ratio: 0.5164
- trades_per_month: 4.2000

### Top guard blocks (events)

| Guard | Blocks |
|---|---:|
| max_trades_per_session | 34 |
| daily_loss_cap | 16 |
| regime_profile | 8 |
| equity_drawdown_kill_switch | 1 |

### Top filter reasons (signal_filtered)

| Reason | Count |
|---|---:|
| position_limit_reached | 34 |
| risk_blocked | 17 |
| regime_blocked | 8 |

### Regime × guard blocks (top)

| Regime | Guard | Blocks |
|---|---|---:|
| trend | max_trades_per_session | 28 |
| trend | daily_loss_cap | 13 |
| compression | regime_profile | 8 |
| expansion | max_trades_per_session | 6 |
| expansion | daily_loss_cap | 3 |
| trend | equity_drawdown_kill_switch | 1 |

### Session × guard blocks (top)

| Session | Guard | Blocks |
|---|---|---:|
| Asia | max_trades_per_session | 13 |
| New York | daily_loss_cap | 10 |
| Overlap | max_trades_per_session | 9 |
| Asia | regime_profile | 8 |
| London | max_trades_per_session | 6 |
| New York | max_trades_per_session | 6 |
| Overlap | daily_loss_cap | 4 |
| Asia | daily_loss_cap | 2 |
| Asia | equity_drawdown_kill_switch | 1 |

## 4. Guard Attribution

| Guard | Blocks | Allows | Trades | Expectancy R | PF | Verdict |
|---|---:|---:|---:|---:|---:|---|
| backtest_pipeline | 0 | 63 | 63 | 0.4286 | 1.8182 | EDGE_PROTECTIVE |
| daily_loss_cap | 16 | 0 | 0 | n/a | n/a | INSUFFICIENT_DATA |
| equity_drawdown_kill_switch | 1 | 0 | 0 | n/a | n/a | INSUFFICIENT_DATA |
| max_trades_per_session | 34 | 0 | 0 | n/a | n/a | UNKNOWN |
| regime_profile | 8 | 0 | 0 | n/a | n/a | INSUFFICIENT_DATA |

## 5. Regime Breakdown

| Regime | Trades | Expectancy R | PF | Sample | Verdict |
|---|---:|---:|---:|---|---|
| compression | 0 | n/a | n/a | INSUFFICIENT_DATA | UNSTABLE |
| expansion | 18 | 0.1667 | 1.2727 | INSUFFICIENT_DATA | PROMISING_BUT_WEAK |
| trend | 45 | 0.5333 | 2.0909 | WEAK_EVIDENCE | PROMISING_BUT_WEAK |

## 6. Session Breakdown

| Session | Trades | Expectancy R | PF | Sample | Verdict |
|---|---:|---:|---:|---|---|
| Asia | 20 | 0.2000 | 1.3333 | WEAK_EVIDENCE | PROMISING_BUT_WEAK |
| London | 7 | 0.7143 | 2.6667 | INSUFFICIENT_DATA | PROMISING_BUT_WEAK |
| New York | 16 | 0.5000 | 2.0000 | INSUFFICIENT_DATA | PROMISING_BUT_WEAK |
| Overlap | 20 | 0.5000 | 2.0000 | WEAK_EVIDENCE | PROMISING_BUT_WEAK |

## 7. Decision Quality

- High quality cycles: 30
- Medium quality cycles: 0
- Low quality cycles: 33
- Unknown cycles: 59

## 8. Warnings

- UNKNOWN_DECISION_QUALITY: {'code': 'UNKNOWN_DECISION_QUALITY', 'count': 59}

## 9. Final Verdict

- Edge verdict: VALIDATION_REQUIRED
- Confidence: LOW
- Main strength: 1 guard(s) show protective behavior
- Main risk: Sample size too small to justify promotion
- Recommended next action: Increase representative sample size before production changes
