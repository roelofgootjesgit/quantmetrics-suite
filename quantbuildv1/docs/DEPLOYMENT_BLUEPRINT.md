# QuantBuild — Deployment Blueprint v1

**Author:** QuantMetrics / Roelof Gootjes
**Date:** March 2026
**Status:** Pre-deployment — validated via 5yr backtest + walk-forward + Monte Carlo

---

## Objective

Transition from validated backtest system to real-money cashflow machine via split deployment architecture.

---

## Core Principle: Split Deployment

Not one system for everything. Two operational envelopes on the same kernel:

| Stack | Purpose | Instruments | Risk Profile |
|-------|---------|-------------|--------------|
| **FUNDED** | Income engine | Core + EURUSD MR | Conservative |
| **CHALLENGE** | Ticket generator | Core + NAS100 + Accelerator | Aggressive |

---

## Funded Stack (Income Engine)

**Config:** `configs/funded.yaml`

**Instruments:**
- XAUUSD — Core trend (alpha driver)
- GBPUSD — Core trend (diversification, TREND only)
- USDJPY — Core trend (volume contributor)
- EURUSD — Mean reversion (COMPRESSION only, stability)

**Risk Parameters:**
- Base risk: 0.5% per trade
- Max daily loss: 2%
- Max total DD: 5%
- NAS100: disabled

**Expected Performance (backtest-validated):**
- ~232 trades/year
- Expectancy: +0.278R
- Monthly return: ~4.0% at 0.5% risk
- R/DD: 10.40
- Max DD: -31R

**Golden Rule:** If funded feels exciting, you're doing it wrong.

---

## Challenge Stack (Ticket Generator)

**Config:** `configs/challenge.yaml`

**Instruments:**
- XAUUSD — Core trend
- GBPUSD — Core trend
- USDJPY — Core trend
- NAS100 — Throughput engine (TREND only, capped)
- EURUSD — Optional (mean reversion)

**Risk Parameters:**
- Base risk: 0.75-1.0% per trade
- Adaptive mode: enabled
- Pass accelerator: enabled (ATTACK/NORMAL/SECURE/COAST)
- NAS100 risk multiplier: 0.5x
- NAS100 max trades/day: 2
- NAS100 max concurrent: 1

**Kill Switches:**
- Daily loss > 2.5%: stop trading for the day
- Total DD > 8%: reset challenge
- Bad week: reduce NAS100 allocation

**Expected Performance (backtest-validated):**
- ~423 trades/year
- FTMO pass rate: ~55% (with NAS100 + accelerator)
- Avg pass time: 9-10 days
- EV per attempt: +$1,191

---

## Account Lifecycle

### Phase 1 — Challenge
- NAS100 active
- Higher risk
- Accelerator active
- Exit condition: +10% reached -> switch to FUNDED

### Phase 2 — Funded
- NAS100 OFF
- EURUSD MR ON
- Lower risk
- Focus: R/DD, not raw PnL

---

## Scaling Model

| Phase | Funded Accounts | Challenge Accounts |
|-------|----------------|--------------------|
| Start | 0 | 1 |
| Pass 1 | 2 | 1 |
| Pass 2 | 4 | 2 |
| Pass 3 | 6-8 | 2-3 |
| Target | 5-10 | 2-3 |

---

## Cashflow Projection

### Per Funded Account (Conservative)
- 4% monthly return
- $100K account
- 80% payout split
- **= ~$2,500 net/month**

### Portfolio Scale
| Accounts | Monthly Net |
|----------|-------------|
| 1 | $2,500 |
| 3 | $7,500 |
| 5 | $12,500 |
| 10 | $25,000 |

---

## Risk Management Rules

### Funded
1. DD > 5% -> stop trading, review
2. 3 consecutive losing days -> halve risk for next 2 days
3. Monthly target reached early -> reduce to 0.25% risk
4. NAS100 NEVER on funded accounts

### Challenge
1. DD > 8% -> reset, don't try to recover
2. Bad week -> reduce NAS100 to 1 trade/day
3. Near target (>7%) -> accelerator switches to SECURE
4. Target reached (>9%) -> COAST mode, minimal risk

### Universal
1. XAU always priority allocation
2. DD protection > profit chasing
3. No parameter changes during live challenge
4. Weekly review, monthly deep analysis

---

## KPI Dashboard (Daily Tracking)

| Metric | Target (Funded) | Target (Challenge) |
|--------|----------------|-------------------|
| Trades/day | 1-2 | 2-4 |
| Daily R | +0.3R | +0.5R |
| Win rate | >50% | >45% |
| Max daily DD | <2% | <2.5% |
| NAS100 impact | N/A | Positive |
| EURUSD MR impact | Positive | Optional |

**Primary metric: R/DD (not absolute PnL)**

---

## Deployment Steps

1. **Paper shadow** (2 weeks) — run both stacks on paper, compare to backtest
2. **Metrics validation** — confirm expectancy, WR, DD within backtest ranges
3. **Micro live** ($1K-$5K personal account) — verify execution quality
4. **First challenge** ($100K FTMO) — challenge stack
5. **Scale** — follow scaling model above

---

## System Architecture

```
Market Data (Dukascopy/Oanda)
    |
    v
REGIME DETECTOR (TREND/EXPANSION/COMPRESSION)
    |
    +---> SQE TREND ENGINE (XAU, GBP, JPY, NAS)
    |         |
    |         v
    |     Dynamic Exits (partial TP, trailing)
    |
    +---> MEAN REVERSION ENGINE (EUR)
    |         |
    |         v
    |     Fixed Exits (1R TP, time stop)
    |
    v
ALLOCATION LAYER
    |
    +---> Adaptive Mode (AGGRESSIVE/BASE/DEFENSIVE/LOCKDOWN)
    +---> Pass Accelerator (ATTACK/NORMAL/SECURE/COAST)
    +---> Portfolio Heat Engine (correlation-aware)
    |
    v
EXECUTION
    |
    +---> Spread/Slippage Guards
    +---> Position Sync
    +---> Telegram Alerts
    +---> Execution Quality Logger
```

---

*This blueprint is based on 5-year validated backtests, walk-forward analysis, Monte Carlo stress testing, and frozen-rules validation. No system is guaranteed — but this one has been built and tested like a professional trading desk.*
