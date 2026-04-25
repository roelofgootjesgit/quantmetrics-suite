# THROUGHPUT COMPARE

*Generated (UTC): 2026-04-25T06:05:45.267791Z*

- experiment_id: `EXP-2021-2025-session-relax-watchlist-v1`
- baseline folder: `b0_baseline`

**Relax-candidate ≠ promotion.** **Watchlist ≠ promotion.** The production promotion gate is unchanged.

## Variant table

| Variant | trades | raw | after_filters | executed | kill_ratio | exp_R | PF | max_dd_R | prot.guard | conf | promote | Δtrades | Δexp | ΔPF | dd/baseline |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---|---|---:|---:|---:|---:|---:|
| b0_baseline | 58 | 167 | 58 | 58 | 0.652694610778443 | 0.2931034482758685 | 1.5151515151515265 | 10.99999999999983 | True | LOW | VALIDATION_REQUIRED | 0.0 | 0.0 | 0.0 | 1.0 |
| b1_london_only_relaxed | 58 | 167 | 58 | 58 | 0.652694610778443 | 0.2931034482758685 | 1.5151515151515265 | 10.99999999999983 | True | LOW | VALIDATION_REQUIRED | 0.0 | 0.0 | 0.0 | 1.0 |
| b2_ny_only_relaxed | 55 | 166 | 55 | 55 | 0.6686746987951807 | 0.25454545454546024 | 1.4375000000000098 | 11.0 | True | LOW | VALIDATION_REQUIRED | -3.0 | -0.038557993730408247 | -0.07765151515151669 | 1.0000000000000155 |
| b3_overlap_relaxed | 58 | 167 | 58 | 58 | 0.652694610778443 | 0.2931034482758685 | 1.5151515151515265 | 10.99999999999983 | True | LOW | VALIDATION_REQUIRED | 0.0 | 0.0 | 0.0 | 1.0 |
| b4_full_session_relaxed | 63 | 122 | 63 | 63 | 0.48360655737704916 | 0.4285714285714302 | 1.8181818181818212 | 10.0 | True | LOW | VALIDATION_REQUIRED | 5.0 | 0.13546798029556173 | 0.30303030303029477 | 0.9090909090909232 |

## Discovery tier rules (canonical)

Single definition for **all** matrices (A0–A5, B0–B4, future presets), vs the **baseline folder** for this run.

### Relax-candidate (strong signal — still not promotion)

Requires **all** of:

- **trades:** strictly greater than baseline × 1.10 (>10% trade count)
- **expectancy_r:** greater than or equal to baseline expectancy R minus 0.08 (material slack)
- **profit_factor:** greater than or equal to 1.25
- **max_drawdown_r:** variant / baseline ratio must be less than or equal to 1.20 (same order of magnitude as QuantOS promotion gate default)
- **confidence:** ordinal must be greater than or equal to baseline (LOW < MEDIUM < HIGH); unknown fails

Includes **max drawdown** and **confidence** vs baseline so relax-tier cannot be earned on throughput + PF alone.

### Watchlist (weak signal — not promotion)

- **trades:** greater than or equal to baseline × 1.05 (≥5% trade count)
- **expectancy_r:** strictly greater than 0
- **profit_factor:** greater than or equal to 1.25

- **Note:** No DD or confidence requirement; not promotion; use only for next experiment design.


## Conclusions (automated triage)

- best_throughput_variant: `b4_full_session_relaxed`
- best_quality_variant: `b4_full_session_relaxed`
- best_balanced_variant: `b4_full_session_relaxed`

### guards_to_keep

- (none)

### guards_to_relax_candidate

- (none)

## Discovery Clusters (interpretive)

Objective **tiers** are unchanged; this section only **summarizes** variants that landed in the same tier with **near-identical** headline metrics (`total_trades`, `expectancy_r`, `profit_factor`, `max_drawdown_r`). **Does not** affect `promotion_decision.json` or tier classification.

*No multi-variant metric clusters in this run.*


## Discovery Watchlist (this run)

Full per-variant strings remain in **JSON** under `conclusions.guards_to_watchlist` and `conclusions.watchlist_by_variant`. Below, **multi-variant clusters** are shown once for readability.

**Unclustered watchlist:**
- B4 pipeline session filter off: discovery watchlist vs `b0_baseline` (~8.6% trade lift, exp>0, PF≥1.25; does not meet full relax gates — not promotion)

### guards_to_investigate (top)

- daily_loss_cap
- equity_drawdown_kill_switch
- max_trades_per_session
- regime_allowed_sessions
- regime_profile

### guards_to_remove_candidate

- (none — removal requires explicit risk review)

### Notes

- Rankings are heuristics for research triage; promotion still requires the hard gate.
- Do not promote on throughput alone; validate expectancy/PF/confidence and sample size.
- guards_to_relax_candidate and guards_to_watchlist are NOT promotion; see discovery_rule_summary.
- discovery_clusters is interpretive reading aid only; it does not change tier labels or promotion_decision.
- Avoid session curve fitting: interpret matrices as throughput vs quality trade-offs vs baseline, not best PF hunting.
