# QuantBuild E1 — Systematic Multi-Asset Trading Engine

A professional-grade algorithmic trading system combining ICT Smart Money Concepts with regime detection, real-time news intelligence, and adaptive capital deployment across multiple instruments.

**84 source files** | **99 passing tests** | **5-year validated backtest** | **3-test validation protocol**

---

## Performance Summary

Backtested on 5 years of 15-minute data (2021-2026) across XAUUSD, GBPUSD, and USDJPY.

| Metric | Challenge Mode | Consistent Mode |
|---|---|---|
| Expectancy | +1.38R per trade | +1.36R per trade |
| Profit Factor | 5.24 | 5.03 |
| Win Rate | 70% | 68% |
| Max Drawdown | -7.1% | -3.4% |
| R/DD Ratio | 21.7 | 29.0 |
| Monthly Average | +15.4% | +9.9% |
| FTMO Pass Rate | 51.4% (10,000 MC sims) | — |

All results include realistic execution simulation (slippage + spread per instrument).

### Validation Protocol — All Tests Passed

| Test | Method | Result | Threshold |
|---|---|---|---|
| Walk-Forward | 12mo train / 6mo test, 8 rolling windows | 62% OOS win rate | 60% |
| Monte Carlo | 5,000 randomized paths + shock injection | 98.5% adaptive wins | 55% |
| Frozen Rules | Zero parameter changes, full sample | R/DD +52%, DD 0.63x | +20%, 1.5x |

---

## Architecture

```
                    Market Data (Dukascopy / Oanda)
                              |
                    +---------v----------+
                    |   Indicator Layer   |  ATR, EMA, Swing Detection
                    +---------+----------+
                              |
                    +---------v----------+
                    |  Regime Detector    |  TREND / EXPANSION / COMPRESSION
                    +---------+----------+
                              |
              +---------------v----------------+
              |        SQE Entry Engine         |  ICT 3-Pillar Model
              |  MSS + Sweep + Displacement     |  Structure + H1 Gate
              +---------------+----------------+
                              |
                    +---------v----------+
                    |     News Gate       |  Event blocking, sentiment boost
                    +---------+----------+
                              |
              +---------------v----------------+
              |    Instrument Profiles          |  Per-market regime gates
              |    XAUUSD / GBPUSD / USDJPY    |  Execution constraints
              +---------------+----------------+
                              |
              +---------------v----------------+
              |    Portfolio Heat Engine         |  Correlation-weighted risk
              |    (not naive position count)    |  Cluster risk prevention
              +---------------+----------------+
                              |
              +---------------v----------------+
              |    Adaptive Mode Layer          |  AGGRESSIVE / BASE /
              |    (equity-curve scaling)       |  DEFENSIVE / LOCKDOWN
              +---------------+----------------+
                              |
              +---------------v----------------+
              |    Execution Layer              |  Oanda v20 broker
              |    Spread/slippage guards       |  Order management
              |    Position monitoring          |  Trailing / partial close
              +---------------+----------------+
                              |
                    +---------v----------+
                    |  Alerts & Dashboard |  Telegram + Streamlit
                    +--------------------+
```

### Core Principle

One universal strategy kernel + instrument-specific execution profiles + adaptive capital deployment. Not multiple systems — one engine with two operating envelopes.

---

## Strategy: SQE (Smart Quality Entry)

Three-pillar ICT entry model:

1. **Trend Context** — Market Structure Shift + Displacement (confirmed directional bias)
2. **Liquidity Levels** — Liquidity Sweep + Fair Value Gaps (institutional order flow)
3. **Entry Trigger** — Displacement confirmation (momentum validation)

Additional filters: H1 structure gate, structure context (HH/HL for longs, LH/LL for shorts), sweep+displacement+FVG combo requirement.

### Dynamic Exit Engine

Regime-aware exits validated through MFE/MAE analysis:

| Regime | Exit Strategy | Rationale |
|---|---|---|
| TREND | Partial at +1R, trail 1.5R from peak | Captures fat-tail winners (median MFE 5.9R) |
| EXPANSION (NY) | Fixed 2R TP / 1R SL | Entry precision is highest here (59% WR, PF 2.91) |
| COMPRESSION | Skip entirely | Negative expectancy, no edge |

---

## Regime Detection

Classifies market state from ATR ratio and price structure:

| Regime | Detection | Trading Rule |
|---|---|---|
| **TREND** | ATR ratio normal, directional structure | Full strategy active |
| **EXPANSION** | ATR ratio > 1.5x, volatility spike | Active only in NY/Overlap sessions (XAUUSD, USDJPY). Disabled for GBPUSD |
| **COMPRESSION** | ATR ratio < 0.7x, range-bound | Blocked — no edge in low volatility |

---

## News Intelligence Layer

Real-time news pipeline with 10 integrated modules:

```
RSS Feeds (Kitco, Reuters, Bloomberg, Fed)
              |
    Normalizer (dedup, topic extraction)
              |
    Relevance Filter (70% semantic + 30% time decay)
              |
    Gold Event Classifier (niche, type, speed)
              |
    Sentiment Engine (rule-based + GPT-4o-mini hybrid)
              |
    News Gate (event blocking + sentiment boost/suppress)
              |
    Counter-News Detector (thesis invalidation on open positions)
```

The news layer operates as a **permission filter**, not a signal generator. It blocks trades around high-impact events (NFP, FOMC, CPI) and boosts/suppresses signal confidence based on sentiment alignment.

---

## Portfolio Engineering

### Promoted Instruments (Data-Validated)

| Instrument | Status | Expectancy | PF | Regime Config |
|---|---|---|---|---|
| XAUUSD | PROMOTE | +0.32R | 1.65 | TREND + EXPANSION (NY only) |
| GBPUSD | PROMOTE | +0.60R | 2.18 | TREND only (EXPANSION disabled) |
| USDJPY | PROMOTE | +0.33R | 1.66 | TREND + EXPANSION |
| XAGUSD | REJECT | — | — | Noisy microstructure |
| EURUSD | WATCHLIST | — | — | Too few trades |

Portfolio correlation between promoted instruments: approximately zero. Zero same-day loss clustering detected across 5-year backtest.

### Correlation-Aware Heat Engine

Replaces naive "max N positions" with portfolio variance calculation:

```
effective_heat = sqrt(sum_i sum_j w_i * w_j * rho_ij)
```

For uncorrelated positions (XAU/GBP/JPY), effective heat is significantly lower than naive heat — real diversification benefit. Prevents hidden cluster risk.

### Adaptive Mode Layer

Equity-curve based risk scaling with four operating modes:

| Mode | Risk Multiplier | Trigger |
|---|---|---|
| AGGRESSIVE | 1.3x | DD < 1%, positive momentum (last 5 trades) |
| BASE | 1.0x | Normal operation |
| DEFENSIVE | 0.6x | DD > 3% or 4+ consecutive losses |
| LOCKDOWN | 0.3x | DD > 5% or 6+ consecutive losses |

Recovery requires consecutive wins to upgrade modes. The adaptive layer adds most value in drawdown/choppy periods — it is a **capital preservation optimizer**, not a return maximizer.

---

## Dual Operating Modes

Same kernel, same instruments, different capital deployment envelope:

| Parameter | Challenge (FTMO) | Consistent |
|---|---|---|
| Risk per trade | 1.5% | 0.75% |
| Max portfolio heat | 6% | 3% |
| Max daily loss | 5% | 2% |
| Max total drawdown | 10% | 6% |
| Target | 10% in 30 days | 3-6% monthly |

---

## Validation & Testing

### Unit Tests

99 tests across 8 test files covering: backtest engine, ICT modules, indicators, live runner, models, news pipeline, portfolio heat engine, adaptive mode layer.

### Validation Protocol v1

Three independent statistical tests that must ALL pass before live deployment:

1. **Walk-Forward** — Rolling 12-month train / 6-month test windows. Adaptive wins 5/8 windows out-of-sample.
2. **Monte Carlo Path Stress** — 5,000 randomized equity paths with correlation shocks and slippage spikes. Adaptive outperforms in 98.5% of paths.
3. **Frozen-Rules No-Touch** — All thresholds locked, zero tuning. R/DD improves +52%, drawdown reduced to 0.63x.

### Paper Shadow Infrastructure

Dual-track evaluator that runs adaptive and static allocators side-by-side on every live signal, logging missed winners, avoided losers, and net block value for post-hoc validation before real capital deployment.

---

## Tech Stack

| Component | Technology |
|---|---|
| Language | Python 3.11 |
| Models | Pydantic v2 (strict typing) |
| Data | Pandas, NumPy, PyArrow (Parquet) |
| Market Data | Dukascopy (5yr history), Oanda v20 (live) |
| News Sources | feedparser (RSS), httpx (API) |
| Sentiment | Rule-based + OpenAI GPT-4o-mini |
| Broker | Oanda v20 (oandapyV20) |
| Alerts | Telegram Bot API |
| Dashboard | Streamlit |
| Config | YAML + Pydantic validation |
| Testing | pytest (99 tests) |

---

## Project Structure

```
quantbuild_e1_v1/
├── src/quantbuild/
│   ├── models/              Pydantic typed models (Trade, Signal, Config)
│   ├── strategy_modules/    ICT modules (8) + News Gate + Regime Detector
│   ├── strategies/          SQE 3-pillar entry engine
│   ├── backtest/            Bar-by-bar engine with MAE/MFE tracking
│   ├── news/                Real-time pipeline (10 modules)
│   ├── execution/           Broker + Adaptive Mode + Heat Engine + Paper Shadow
│   ├── indicators/          Centralized: ATR, EMA, SMA, Swing Detection
│   ├── alerts/              Telegram notifications
│   ├── dashboard/           Streamlit web UI
│   ├── data/                Session logic, schemas
│   └── io/                  Parquet loader, Oanda/Dukascopy feeds
├── scripts/                 13 analysis & validation scripts
├── configs/                 YAML configs + instrument profiles
├── tests/                   99 unit tests (8 files)
└── reports/                 JSON output from backtests & validation
```

---

## Quick Start

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env

# Run tests
pytest tests/ -v

# Backtest (5-year, multi-instrument)
python scripts/portfolio_adaptive_sim.py

# Validation protocol
python scripts/validation_protocol.py

# Live paper shadow
python -m src.quantbuild.app --config configs/strict_prod_v2.yaml live --dry-run
```

### cTrader Demo via QuantBridge Bridge

Use this when you want QuantBuild to execute through `quantBridge-v.1` OpenAPI transport.

```bash
# Optional when quantBridge-v.1 is not in sibling folder:
set QUANTBRIDGE_SRC_PATH=C:\path\to\quantBridge-v.1\src

# Smoke test: connect -> price -> place -> close
python scripts/ctrader_smoke.py --config configs/ctrader_quantbridge_openapi.yaml --units 100

# Safe launch (preflight + optional recovery + heartbeat + timeout)
python scripts/launch_live_safe.py --config configs/ctrader_quantbridge_openapi.yaml --max-runtime-seconds 1800 --heartbeat-seconds 30

# Preflight only (no live process)
python scripts/launch_live_safe.py --config configs/ctrader_quantbridge_openapi.yaml --dry-launch
```

---

## Deployment Roadmap

| Phase | Status | Description |
|---|---|---|
| Core kernel | Done | SQE entries, regime detection, dynamic exits, indicators |
| News intelligence | Done | RSS pipeline, sentiment, news gate, counter-news |
| Cross-instrument validation | Done | 5 instruments tested, 3 promoted, 2 rejected |
| Portfolio engineering | Done | Heat engine, adaptive mode, execution guards |
| Statistical validation | Done | Walk-forward, Monte Carlo, frozen-rules — all passed |
| Paper shadow | Ready | Infrastructure built, acceptance thresholds defined |
| Micro-live | Next | Small capital validation with full logging |
| Funded deployment | Planned | FTMO challenge + funded account operation |
