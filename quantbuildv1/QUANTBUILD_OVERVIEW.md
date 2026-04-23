# QuantBuild E1 — Technical Overview

## System Summary

QuantBuild E1 is a systematic multi-asset trading engine that combines ICT Smart Money Concepts with regime-aware filtering, real-time news intelligence, and adaptive portfolio-level capital deployment.

The system operates as a single decision kernel deployed across multiple instruments with per-market execution profiles and equity-curve-based risk scaling.

**84 source files** | **13 analysis scripts** | **5 config profiles** | **99 unit tests** | **3-test validation protocol**

---

## Edge Structure (Four Layers)

### Layer 1 — Strategy Edge

The core kernel uses the SQE (Smart Quality Entry) three-pillar ICT model:

| Pillar | Components | Logic |
|---|---|---|
| Trend Context | Market Structure Shift, Displacement | Confirmed directional bias required |
| Liquidity Levels | Liquidity Sweep, Fair Value Gaps | Institutional order flow evidence |
| Entry Trigger | Displacement confirmation | Momentum validation gate |

Additional filters: H1 higher-timeframe structure gate, structure context filtering (HH/HL for longs, LH/LL for shorts), minimum 2-of-3 sweep+displacement+FVG combination.

### Layer 2 — Regime Edge

Market classified into three states with different trading rules:

| Regime | Detection | Exit Strategy |
|---|---|---|
| TREND | ATR ratio normal, directional structure | Partial +1R, trail 1.5R from peak (captures median 5.9R MFE) |
| EXPANSION | ATR > 1.5x SMA, volatility spike | Fixed 2R TP (59% WR, PF 2.91) |
| COMPRESSION | ATR < 0.7x SMA, range-bound | Blocked — no edge |

Regime gates are instrument-specific: GBPUSD has EXPANSION disabled (0% WR in expansion).

### Layer 3 — Portfolio Edge

Three promoted instruments with near-zero cross-correlation:

| Instrument | Edge | PF | Config |
|---|---|---|---|
| XAUUSD | +0.32R, 254 trades/5yr | 1.65 | TREND + EXPANSION (NY/Overlap, 10+ UTC) |
| GBPUSD | +0.60R, 61 trades/5yr | 2.18 | TREND only |
| USDJPY | +0.33R, 142 trades/5yr | 1.66 | TREND + EXPANSION |

Portfolio-level: zero same-day loss clustering. R/DD ratio of 7.5 as a combined portfolio.

### Layer 4 — Capital Deployment Edge

Correlation-aware heat engine + adaptive mode layer:

| Mode | Risk Multiplier | Trigger |
|---|---|---|
| AGGRESSIVE | 1.3x | DD < 1%, positive 5-trade momentum |
| BASE | 1.0x | Normal operation |
| DEFENSIVE | 0.6x | DD > 3% or 4+ consecutive losses |
| LOCKDOWN | 0.3x | DD > 5% or 6+ consecutive losses |

The adaptive layer is a capital preservation optimizer. Walk-forward validated: wins 5/8 out-of-sample windows. Monte Carlo validated: wins 98.5% of 5,000 randomized paths.

---

## News Intelligence Pipeline

```
RSS Feeds (6 sources: Kitco, Reuters, Bloomberg, CNBC, Fed)
    |
    v
Normalizer → Dedup (MD5 hash) → Topic Extraction
    |
    v
Relevance Filter (70% semantic + 30% time decay)
    |
    v
Gold Event Classifier → Niche / Type / Impact Speed
    |
    v
Sentiment Engine (Rule-based + GPT-4o-mini hybrid, fallback)
    |
    v
News Gate → Blocks trading 30min before / 15min after: NFP, FOMC, CPI, GDP
    |         Boosts signal confidence when sentiment > 0.7 aligns with direction
    |         Suppresses signal when sentiment < 0.3 contradicts direction
    v
Counter-News Detector → Monitors open positions for thesis invalidation
```

News operates as a **filter and gating layer**, not a signal generator. Used for defensive blocking and confidence adjustment.

---

## Execution Infrastructure

### Live Runner Decision Loop

```
Every 60 seconds:
  1. Reset daily tracking (if new day)
  2. Update regime from latest 15m/1h OHLC
  3. Poll news, check for high-impact events
  4. Sync open positions with broker
  5. Evaluate SQE signals on latest bar
  6. For each signal:
     - Check regime gate (per instrument profile)
     - Check news gate
     - Check spread guard
     - Check position limit
     - Check daily loss limit
     - Calculate SL/TP from current ATR
     - Submit order (or dry-run log)
     - Verify slippage within bounds
  7. Monitor open positions (trailing, thesis check)
```

### Execution Guards

| Guard | Default | Purpose |
|---|---|---|
| Max spread | Per instrument (1.5-4.0 pips) | Reject in wide-spread conditions |
| Max slippage | Per instrument (0.10-0.15R) | Reject if fill quality degrades |
| Max open positions | 3 | Prevent over-concentration |
| Max daily loss | 5% (challenge) / 2% (consistent) | Hard daily stop |
| Max total DD | 10% (challenge) / 6% (consistent) | Account preservation |

### Order Management

- Break-even: SL moves to entry when trade reaches trigger R
- Partial close: Configurable percentage at target R
- Trailing stop: Follows price at configurable distance
- State persisted to JSON for crash recovery

---

## Configuration Architecture

### Universal Kernel Config

`configs/strict_prod_v2.yaml` — Strategy parameters, regime thresholds, session filters.

### Instrument Profiles

`configs/instruments/instrument_profiles.yaml` — Per-instrument execution constraints, regime gates, promotion status.

### Operating Modes

Defined in instrument profiles under `modes`:

| Parameter | Challenge | Consistent |
|---|---|---|
| Risk/trade | 1.5% | 0.75% |
| Max heat | 6% | 3% |
| Max daily loss | 5% | 2% |
| Max total DD | 10% | 6% |
| Max correlated exposure | 2 | 2 |

---

## Validation Results

### Backtest Performance (5 years, 2021-2026)

| Config | Trades | WR | PF | Exp/R | Total% | MaxDD | R/DD |
|---|---|---|---|---|---|---|---|
| Challenge Adaptive | 79 | 70% | 5.24 | +1.38R | +154% | -7.1% | 21.7 |
| Challenge Static | 76 | 64% | 4.30 | +1.24R | +141% | -11.1% | 12.8 |
| Consistent Adaptive | 85 | 68% | 5.03 | +1.36R | +99% | -3.4% | 29.0 |
| Consistent Static | 80 | 65% | 4.37 | +1.25R | +75% | -6.4% | 11.7 |

### Validation Protocol v1

All three tests passed with frozen parameters:

**Walk-Forward**: 8 rolling windows (12mo train, 6mo test). Adaptive wins 5/8 (62%). Primary value in drawdown/choppy periods — adaptive avg max DD -7.3% vs static -10.6%.

**Monte Carlo**: 5,000 randomized paths with 10% correlation shock probability and 5% delayed recovery injection. Adaptive wins 98.5%. P5 R/DD delta: +2.5 (even worst-case paths, adaptive is better).

**Frozen Rules**: Zero parameter changes. R/DD improvement +52.3%. Drawdown reduction to 0.63x of static. Confirms thresholds are not overfit.

### FTMO Challenge Analysis

| Metric | Value |
|---|---|
| Pass rate | 51.4% (10,000 Monte Carlo sims) |
| Fail reason | 49% timeout, <1% DD blow |
| Avg days to pass | 17 |
| EV per attempt | +$5,157 |

---

## Analysis Scripts

| Script | Purpose |
|---|---|
| `portfolio_adaptive_sim.py` | Full simulation: adaptive vs static, both modes, FTMO EV |
| `validation_protocol.py` | Walk-forward + MC stress + frozen rules validation |
| `portfolio_dual_mode.py` | Dual-mode (challenge + consistent) portfolio simulation |
| `cross_instrument_runner.py` | Multi-instrument kernel test + promotion rubric |
| `robustness_and_ftmo.py` | Slippage stress test + FTMO probability model |
| `production_analysis.py` | Segment-specific exits + Monte Carlo + scaling projection |
| `trailing_stop_research.py` | MFE-driven trailing stop comparison (4 variants) |
| `exit_analytics.py` | MAE/MFE analysis + exit variant simulation |
| `regime_analytics.py` | 8-section per-regime performance deep dive |
| `strategy_variants_backtest.py` | STRICT/MEDIUM/LIGHT variant comparison |
| `collect_news.py` | Continuous news collection to Parquet |
| `ab_test_news.py` | ICT-only vs ICT+news A/B comparison |
| `fetch_dukascopy_xauusd.py` | Historical data download |

---

## Test Coverage

```
99 tests passing — 0 failures

tests/test_adaptive_mode.py     11 tests   Mode transitions, recovery, scaling
tests/test_portfolio_heat.py    10 tests   Correlation heat, blocking, limits
tests/test_live_runner.py       13 tests   Signal wiring, guardrails, regime skip
tests/test_indicators.py        11 tests   ATR, swing, pivot, MA calculations
tests/test_backtest.py           6 tests   Metrics, trade simulation, cache
tests/test_ict_modules.py       10 tests   All 8 ICT modules + structure
tests/test_models.py            16 tests   Trade, Signal, Config, R:R calculation
tests/test_news.py              22 tests   Full pipeline: normalize to counter-news
```

---

## Deployment Status

| Component | Status |
|---|---|
| Strategy kernel (SQE + ICT) | Production-ready |
| Regime detector | Production-ready, live-wired |
| Dynamic exit engine | Validated (MFE-driven) |
| News intelligence | Production-ready |
| Instrument profiles | Data-validated (3 promoted) |
| Portfolio heat engine | Validated (correlation-aware) |
| Adaptive mode layer | Validated (3-test protocol passed) |
| Execution guards | Production-ready |
| Paper shadow evaluator | Built, ready for deployment |
| Live execution (Oanda) | Infrastructure complete |
| Telegram alerts | Built |
| Streamlit dashboard | Built |

### Next Phase: Paper Shadow Observation

The system is entering live paper shadow mode with frozen parameters. Acceptance gates at 30, 50, and 100 trades determine progression to micro-live and funded deployment. See `docs/PAPER_SHADOW_ACCEPTANCE.md` for the full acceptance framework.
