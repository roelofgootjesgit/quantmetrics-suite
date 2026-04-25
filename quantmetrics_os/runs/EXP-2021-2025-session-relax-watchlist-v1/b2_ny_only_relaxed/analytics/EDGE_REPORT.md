# EDGE REPORT

## 1. Run Summary

- Run ID: qb_run_20260425T055514Z_7a7f7a73
- Source events: C:\Users\Gebruiker\quantmetrics-suite\quantbuild\data\quantlog_events\runs\qb_run_20260425T055514Z_7a7f7a73.jsonl
- Total events: 995
- Total decision cycles: 166
- Completed cycles: 166
- Incomplete cycles: 0
- Output path: C:\Users\Gebruiker\quantmetrics-suite\quantmetrics_os\runs\EXP-2021-2025-session-relax-watchlist-v1\b2_ny_only_relaxed\analytics

## 2. Performance Summary

- Total trades: 55
- Expectancy R: 0.2545
- Win rate: 0.4182
- Profit factor: 1.4375
- Max drawdown R: 10.0000

## 3. Throughput Funnel (Diagnostics)

- raw_signals_detected: 166
- signals_after_filters: 55
- signals_executed: 55
- filter_kill_ratio: 0.6687
- execution_ratio: 0.3313
- trades_per_month: 2.8947

### Top guard blocks (events)

| Guard | Blocks |
|---|---:|
| regime_allowed_sessions | 57 |
| max_trades_per_session | 24 |
| regime_profile | 15 |
| daily_loss_cap | 14 |
| equity_drawdown_kill_switch | 1 |

### Top filter reasons (signal_filtered)

| Reason | Count |
|---|---:|
| session_blocked | 57 |
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
| expansion | regime_allowed_sessions | 11 |
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
| Overlap | regime_allowed_sessions | 2 |
| London | equity_drawdown_kill_switch | 1 |

## 4. Guard Attribution

| Guard | Blocks | Allows | Trades | Expectancy R | PF | Verdict |
|---|---:|---:|---:|---:|---:|---|
| backtest_pipeline | 0 | 55 | 55 | 0.2545 | 1.4375 | EDGE_PROTECTIVE |
| daily_loss_cap | 14 | 0 | 0 | n/a | n/a | INSUFFICIENT_DATA |
| equity_drawdown_kill_switch | 1 | 0 | 0 | n/a | n/a | INSUFFICIENT_DATA |
| max_trades_per_session | 24 | 0 | 0 | n/a | n/a | UNKNOWN |
| regime_allowed_sessions | 57 | 0 | 0 | n/a | n/a | UNKNOWN |
| regime_profile | 15 | 0 | 0 | n/a | n/a | INSUFFICIENT_DATA |

## 5. Regime Breakdown

| Regime | Trades | Expectancy R | PF | Sample | Verdict |
|---|---:|---:|---:|---|---|
| compression | 0 | n/a | n/a | INSUFFICIENT_DATA | UNSTABLE |
| expansion | 13 | 0.1538 | 1.2500 | INSUFFICIENT_DATA | PROMISING_BUT_WEAK |
| trend | 42 | 0.2857 | 1.5000 | WEAK_EVIDENCE | PROMISING_BUT_WEAK |

## 6. Session Breakdown

| Session | Trades | Expectancy R | PF | Sample | Verdict |
|---|---:|---:|---:|---|---|
| Asia | 0 | n/a | n/a | INSUFFICIENT_DATA | UNSTABLE |
| London | 8 | 0.5000 | 2.0000 | INSUFFICIENT_DATA | PROMISING_BUT_WEAK |
| New York | 22 | 0.2273 | 1.3846 | WEAK_EVIDENCE | PROMISING_BUT_WEAK |
| Overlap | 25 | 0.2000 | 1.3333 | WEAK_EVIDENCE | PROMISING_BUT_WEAK |

## 7. Decision Quality

- High quality cycles: 23
- Medium quality cycles: 0
- Low quality cycles: 32
- Unknown cycles: 111

## 8. Warnings

- UNKNOWN_DECISION_QUALITY: {'code': 'UNKNOWN_DECISION_QUALITY', 'count': 111}

## 9. Final Verdict

- Edge verdict: VALIDATION_REQUIRED
- Confidence: LOW
- Main strength: 1 guard(s) show protective behavior
- Main risk: Sample size too small to justify promotion
- Recommended next action: Increase representative sample size before production changes
