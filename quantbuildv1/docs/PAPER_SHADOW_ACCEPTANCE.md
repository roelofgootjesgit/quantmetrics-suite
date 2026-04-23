# Paper Shadow Acceptance Framework

Live validation protocol for the adaptive allocator before real capital deployment.

Every signal is evaluated through **both** the adaptive allocator and the static baseline. Neither executes real trades. This is pure observation with structured acceptance gates.

---

## Core Metrics (Logged Per Trade)

| Metric | Description |
|---|---|
| `timestamp` | Signal time (UTC) |
| `symbol` | Instrument |
| `direction` | LONG / SHORT |
| `regime` | TREND / EXPANSION |
| `session` | London / NY / Overlap |
| `adaptive_mode` | AGGRESSIVE / BASE / DEFENSIVE / LOCKDOWN |
| `adaptive_risk_pct` | Effective risk after mode scaling |
| `static_risk_pct` | Fixed risk (no mode scaling) |
| `adaptive_action` | TRADE / BLOCK / SKIP |
| `static_action` | TRADE / BLOCK |
| `block_reason` | heat_limit / daily_loss / lockdown / spread / slippage |
| `effective_heat` | Portfolio heat at time of signal |
| `signal_pnl_r` | Realized PnL of the signal (regardless of allocation) |
| `adaptive_pnl_pct` | Hypothetical equity impact (adaptive) |
| `static_pnl_pct` | Hypothetical equity impact (static) |
| `delta_pnl_pct` | Adaptive minus static |
| `realized_slippage` | Actual vs expected fill |
| `realized_spread` | Actual spread at signal time |

---

## Top-Level Decision Metric

### Net Block Value (NBV)

```
NBV = avoided_loser_R - missed_winner_R
```

This is the single most important metric. If NBV stays positive, the adaptive layer is doing its job: blocking more bad trades than good ones.

---

## Review Gates

### Gate 1 — After 30 Trades

**Purpose**: Early sanity check. Detect catastrophic failures before accumulating more data.

| Metric | Threshold | Action if Failed |
|---|---|---|
| Net Block Value | > -2R | If < -2R: pause and investigate |
| Adaptive max DD | <= Static max DD | If worse: check mode transition logic |
| Realized slippage | < 0.2R average | If higher: tighten execution guards |
| Spread rejections | < 20% of signals | If higher: review instrument profiles |
| LOCKDOWN triggers | < 3 total | If excessive: check threshold calibration |

**Decision**: CONTINUE / PAUSE / RECALIBRATE

This gate is not about performance. It's about confirming the system behaves as designed.

### Gate 2 — After 50 Trades

**Purpose**: Statistical significance starts. Compare adaptive vs static with enough sample.

| Metric | Threshold | Action if Failed |
|---|---|---|
| Net Block Value | > 0R | Adaptive must net-positive block |
| Adaptive R/DD | > Static R/DD | Core thesis: better risk-adjusted |
| Adaptive max DD | <= 110% of Static DD | Small tolerance, not worse |
| DEFENSIVE mode trades | Positive or neutral avg PnL | Defensive should preserve, not destroy |
| AGGRESSIVE mode trades | Higher avg PnL than BASE | Aggression must earn its keep |
| Per-instrument slippage | Within profile limits | Execution assumptions validated |

**Decision**: CONTINUE / DEMOTE TO STATIC / ADJUST THRESHOLDS

If adaptive R/DD < static R/DD at 50 trades, the adaptive layer does not graduate.

### Gate 3 — After 100 Trades

**Purpose**: Promotion decision. Enough data to make a real call.

| Metric | Threshold | Action if Failed |
|---|---|---|
| Net Block Value | > +3R cumulative | Clear positive blocking value |
| Adaptive total return | Within 15% of static | Not sacrificing too much upside |
| Adaptive max DD | < Static max DD | DD reduction confirmed live |
| R/DD improvement | > +10% vs static | Meaningful risk-adjusted improvement |
| Mode accuracy | > 60% correct mode transitions | Modes switch at the right times |
| Blocked trade avg PnL | Negative or neutral | Blocked trades were mostly bad |
| Missed winner rate | < 30% of total blocks | Not blocking too many winners |

**Decision**: PROMOTE TO MICRO-LIVE / CONTINUE PAPER / DEMOTE

---

## Per-Mode Evaluation

Each adaptive mode is evaluated independently:

### AGGRESSIVE
- Should have higher avg PnL than BASE
- Should occur during low-DD, positive momentum periods
- If AGGRESSIVE avg PnL < BASE avg PnL: mode is not earning its premium

### BASE
- Benchmark performance
- Should be the most common mode (40-60% of trades)

### DEFENSIVE
- Should have lower DD contribution than BASE
- Avg PnL may be lower, but DD-per-trade should be significantly lower
- If DEFENSIVE trades have same DD as BASE: mode is not protecting

### LOCKDOWN
- Should be rare (< 5% of total signals)
- Should only trigger during genuine equity crises
- If LOCKDOWN blocks > 10% of signals: thresholds too sensitive

---

## Execution Quality Gates

| Metric | Per Instrument | Action |
|---|---|---|
| Avg slippage | < max_slippage_r from profile | If exceeded: widen guard or reduce risk |
| Spread rejection rate | < 15% | If exceeded: check session timing |
| Fill quality score | A or B | If C or F: investigate broker quality |
| Slippage drift | No upward trend over time | If trending up: market conditions changing |

---

## Freeze Protocol

From the start of paper shadow until Gate 3 decision:

- **NO** adaptive threshold changes
- **NO** mode trigger adjustments
- **NO** heat limit modifications
- **NO** recovery criteria updates
- **NO** instrument profile changes

Any parameter change invalidates the paper shadow data and requires restart.

---

## Promotion Path

```
Paper Shadow (30 → 50 → 100 trades)
        |
        v
    Gate 3 PASS?
   /           \
  YES           NO
  |              |
  v              v
Micro-Live    Continue Paper
($500-1k)     (another 50 trades)
  |
  v
50 live trades
  |
  v
Funded Deployment
(FTMO Challenge)
```

### Micro-Live Rules

- Maximum capital: $1,000
- Risk per trade: 0.5% (half of backtest)
- All logging continues
- Same acceptance thresholds apply
- Duration: minimum 50 trades or 30 days

### Funded Deployment Criteria

- Micro-live R/DD > 80% of paper shadow R/DD
- Realized slippage within 120% of simulation
- No LOCKDOWN events during micro-live
- Net Block Value remains positive

---

## Timeline Estimate

Based on current trade frequency (~0.4 trades/day across 3 instruments):

| Gate | Trades | Estimated Days |
|---|---|---|
| Gate 1 | 30 | ~75 days |
| Gate 2 | 50 | ~125 days |
| Gate 3 | 100 | ~250 days |

This is conservative. If EURUSD is promoted from watchlist, frequency increases and timelines compress.

---

## Failure Modes

| Scenario | Response |
|---|---|
| Adaptive consistently blocks winners | Reduce DEFENSIVE sensitivity |
| LOCKDOWN triggers too often | Raise lockdown_dd threshold |
| Execution quality degrades | Tighten spread/slippage guards |
| Correlation spike between instruments | Temporarily reduce max_correlated_exposure |
| Single instrument dominates losses | Disable instrument, do not re-optimize |
| Mode oscillation (rapid AGGRESSIVE ↔ DEFENSIVE) | Increase recovery_wins requirement |
