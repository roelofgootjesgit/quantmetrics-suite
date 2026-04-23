# quantbuild

Strategy and risk engine for the Quant suite (siblings: **`quantmetrics_os`**, **`quantbridge`**, **`quantlog`**, **`quantanalytics`**).

**quantbuild** is responsible for one thing: processing market data and producing 
trade decisions. It does not place orders, does not store events, and does not 
manage broker connections. Those concerns live in **`quantbridge`** and **`quantlog`**.

**84 source files · 99 tests · 8 test files**

---

## Design principle

Strategy and risk are separated by design. Signal generation, regime 
classification, and portfolio heat calculation are independent modules. 
Each can be tested, replaced, or extended without touching the others.

Execution is a boundary — **quantbuild** produces decisions, **quantbridge** 
acts on them. No broker API calls exist anywhere in this codebase.

---

## Modularity

**quantbuild** is built around a single interface: `IStrategyModule`. Every 
component that produces or filters a signal implements this interface. 
Swapping a strategy means swapping a module — nothing else changes.
IStrategyModule
│
├── RegimeDetector        # classify market state
├── SQEEntryEngine        # 3-pillar ICT signal model (default)
├── NewsGate              # permission filter
├── PortfolioHeatEngine   # risk sizing
└── AdaptiveModeLayer     # equity-curve scaling

To run a different strategy:
- Implement `IStrategyModule`
- Register it in the YAML config
- The engine, risk layer, and execution boundary stay unchanged

Instrument profiles, regime gates, and capital constraints are all 
YAML-configurable — no code changes required to add a new market 
or adjust operating parameters.

---

## Architecture
Market Data (Dukascopy / Oanda / cTrader)
│
┌─────────▼──────────┐
│   Indicator Layer   │  ATR, EMA, Swing Detection (centralized)
└─────────┬──────────┘
│
┌─────────▼──────────┐
│   Regime Detector   │  TREND / EXPANSION / COMPRESSION
└─────────┬──────────┘
│
┌─────────▼──────────┐
│   SQE Entry Engine  │  3-pillar signal model
│   (strategy_modules)│  MSS + Sweep + Displacement + H1 gate
└─────────┬──────────┘
│
┌─────────▼──────────┐
│    News Gate        │  Permission filter — blocks or boosts signals
│    (10 modules)     │  RSS → normalize → classify → sentiment → gate
└─────────┬──────────┘
│
┌─────────▼──────────┐
│  Instrument Profiles│  Per-market regime gates and constraints
└─────────┬──────────┘
│
┌─────────▼──────────┐
│  Portfolio Heat     │  Correlation-weighted risk (not naive position count)
│  Engine             │  effective_heat = sqrt(Σ w_i * w_j * ρ_ij)
└─────────┬──────────┘
│
┌─────────▼──────────┐
│  Adaptive Mode      │  Equity-curve scaling: AGGRESSIVE / BASE /
│  Layer              │  DEFENSIVE / LOCKDOWN
└─────────┬──────────┘
│
┌─────────▼──────────┐
│  Execution boundary │  Trade decisions passed to quantbridge
│  (no broker calls)  │  Paper shadow runs in parallel for validation
└────────────────────┘

---

## Module breakdown

### Indicators (`indicators/`)
Centralized indicator library: ATR, EMA, SMA, swing detection. All strategy 
modules consume from here — no duplicated calculations across the codebase.

### Regime Detector (`strategy_modules/`)
Classifies market state per bar from ATR ratio and price structure:

| Regime | Condition | Trading rule |
|--------|-----------|--------------|
| TREND | ATR ratio normal, directional structure | Full strategy active |
| EXPANSION | ATR ratio > 1.5x | Active NY/Overlap only (XAUUSD, USDJPY). Disabled for GBPUSD |
| COMPRESSION | ATR ratio < 0.7x | Blocked — no edge |

### SQE Entry Engine (`strategies/`)
Three-pillar signal model. All three must be present for a signal to emit:
1. Market Structure Shift + Displacement (directional bias)
2. Liquidity Sweep + Fair Value Gap (institutional order flow)
3. Displacement confirmation (momentum validation)

Additional gate: H1 structure context. HH/HL required for longs, LH/LL for shorts.

### News Gate (`news/`)
10-module pipeline operating as a permission filter, not a signal source:
RSS (Kitco, Reuters, Bloomberg, Fed)
→ normalize + dedup
→ relevance filter (70% semantic / 30% time decay)
→ event classifier (type, speed, niche)
→ sentiment engine (rule-based + GPT-4o-mini hybrid)
→ gate (block / boost / suppress)
→ counter-news detector (invalidates thesis on open positions)

### Portfolio Heat Engine (`execution/`)
Replaces naive position counting with portfolio variance:
effective_heat = sqrt(Σᵢ Σⱼ wᵢ * wⱼ * ρᵢⱼ)
For uncorrelated instruments (XAUUSD / GBPUSD / USDJPY), effective heat 
is materially lower than naive heat — real diversification, not assumed.

### Adaptive Mode Layer (`execution/`)
Four-state equity-curve risk scaler:

| Mode | Multiplier | Trigger |
|------|-----------|---------|
| AGGRESSIVE | 1.3x | DD < 1%, positive momentum |
| BASE | 1.0x | Normal |
| DEFENSIVE | 0.6x | DD > 3% or 4+ consecutive losses |
| LOCKDOWN | 0.3x | DD > 5% or 6+ consecutive losses |

Recovery requires consecutive wins to upgrade. Capital preservation optimizer, 
not a return maximizer.

### Paper Shadow (`execution/`)
Dual-track evaluator running adaptive and static allocators in parallel on 
every live signal. Logs missed winners, avoided losers, and net block value 
for post-hoc validation before real capital deployment.

---

## Project structure
src/quantbuild/
├── models/           Pydantic v2 typed models (Trade, Signal, Config)
├── strategy_modules/ ICT modules (8) + Regime Detector + News Gate
├── strategies/       SQE entry engine
├── backtest/         Bar-by-bar engine with MAE/MFE tracking
├── news/             Real-time pipeline (10 modules)
├── execution/        Adaptive Mode + Heat Engine + Paper Shadow
├── indicators/       Centralized: ATR, EMA, SMA, Swing Detection
├── alerts/           Telegram notifications
├── dashboard/        Streamlit web UI
├── data/             Session logic, schemas
└── io/               Parquet loader, Oanda/Dukascopy/cTrader feeds
scripts/              13 analysis and validation scripts
configs/              YAML configs + instrument profiles
tests/                99 unit tests (8 files)
reports/              JSON output from backtests and validation

---

## Testing

99 tests across 8 files covering: backtest engine, ICT modules, indicators, 
live runner, models, news pipeline, portfolio heat engine, adaptive mode layer.
pytest tests/ -v

Three-test validation protocol (walk-forward, Monte Carlo, frozen-rules) 
documented in `scripts/validation_protocol.py`.

---

## Quick start
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
Tests
pytest tests/ -v
Dry-run (Oanda)
python -m src.quantbuild.app --config configs/strict_prod_v2.yaml live --dry-run
Dry-run (cTrader via quantbridge)
python -m src.quantbuild.app --config configs/demo_strict_ctrader.yaml live --dry-run

Set `QUANTBRIDGE_SRC_PATH` in `.env` when running with cTrader.  
See `docs/CREDENTIALS_AND_ENVIRONMENT.md` for full environment setup.

---

## Market data routing

```yaml
data:
  source: auto   # auto | ctrader | dukascopy | yfinance
```

`auto` tries cTrader → Dukascopy → yfinance. Execution provider and 
data source are independent — configurable separately per YAML.

---

## QuantAnalytics after backtest

When **`quantlog.enabled`** is on (default) and **`quantlog.auto_analytics`** is **true** (default in `configs/default.yaml`), each finished **backtest** runs **`quantmetrics_analytics.cli.run_analysis`** on your QuantLog tree (`quantlog.base_path`). Unless you already set **`QUANTMETRICS_ANALYTICS_OUTPUT_DIR`**, QuantBuild passes **`QUANTMETRICS_ANALYTICS_OUTPUT_DIR`** pointing at **``../quantanalytics/output_rapport/``** (direct sibling of **`quantbuild`** only — same parent directory). Deeper monorepos: set the env var yourself. Set **`QUANTMETRICS_ANALYTICS_AUTO=0`** or **`quantlog.auto_analytics: false`** to skip; pytest sets **`QUANTMETRICS_ANALYTICS_AUTO=0`** automatically.

---

## Suite

| Repo | GitHub |
|-----------|------------|
| `quantmetrics_os` | [roelofgootjesgit/quantmetrics_os](https://github.com/roelofgootjesgit/quantmetrics_os) |
| `quantbuild` (**this**) | [roelofgootjesgit/QuantBuild-Signal-Engine](https://github.com/roelofgootjesgit/QuantBuild-Signal-Engine) |
| `quantbridge` | [roelofgootjesgit/quantbridgev1](https://github.com/roelofgootjesgit/quantbridgev1) |
| `quantlog` | [roelofgootjesgit/quantlogv1](https://github.com/roelofgootjesgit/quantlogv1) |
| `quantanalytics` | [roelofgootjesgit/quantanalyticsv1](https://github.com/roelofgootjesgit/quantanalyticsv1) |
