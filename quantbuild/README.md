# quantbuild

## SYSTEM IDENTITY

This module is part of the QuantMetrics suite.
- Canonical name: `quantbuild`
- Role: Decision Engine

`quantbuild` processes market data into trade decisions. It owns strategy and risk logic, and delegates execution to `quantbridge` and event storage to `quantlog`.

---

## Core responsibility

- Generate and filter signals through modular strategy components.
- Apply risk logic (portfolio heat, adaptive mode, trade constraints).
- Run backtests and dry/live decision loops without broker API coupling.
- Emit decision events for downstream observability and analytics.

Design boundary: `quantbuild` decides, `quantbridge` executes.

---

## Architecture

```text
Market data -> indicators -> regime -> strategy -> news gate -> risk engines -> decision output
```

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

## Suite path policy (required)

Production layout expects one canonical suite root with sibling repos:
`quantbuild`, `quantbridge`, `quantlog`, `quantanalytics`, and `quantmetrics_os`.

Environment values used by this layout:
- `QUANTMETRICS_OS_ROOT`
- `QUANTLOG_REPO_PATH`
- `QUANTBRIDGE_SRC_PATH`
- `QUANTMETRICS_ANALYTICS_OUTPUT_DIR`

Quick check:

```bash
python scripts/check_suite_layout.py
```

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

## Notes

- `data.source: auto` tries cTrader -> Dukascopy -> yfinance.
- With `quantlog.auto_analytics: true`, finished backtests can auto-run `quantanalytics`.
- With `artifacts.enabled: true`, post-backtest artifacts are copied to `quantmetrics_os/runs/...`.

---

## Documentation

- `docs/CREDENTIALS_AND_ENVIRONMENT.md`
- `scripts/validation_protocol.py`
- `../quantmetrics_os/docs/RUN_ARTIFACT_STRATEGY.md`

---

## Suite repositories (GitHub)

| Repo | GitHub |
|-----------|------------|
| `quantmetrics_os` | [roelofgootjesgit/quantmetrics_os](https://github.com/roelofgootjesgit/quantmetrics_os) |
| `quantbuild` (**this**) | [roelofgootjesgit/QuantBuild-Signal-Engine](https://github.com/roelofgootjesgit/QuantBuild-Signal-Engine) |
| `quantbridge` | canonical module: `quantbridge` |
| `quantlog` | canonical module: `quantlog` |
| `quantanalytics` | canonical module: `quantanalytics` |
