# Quantbuild E1 v1 — XAUUSD Full-Stack Trading Bot

ICT-based XAUUSD (gold) trading system with real-time news integration,
backtesting, live execution via Oanda, and Telegram alerts.

## Quick Start

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt
cp .env.example .env            # fill in credentials

# Fetch data & run backtest
python -m src.quantbuild.app --config configs/xauusd.yaml fetch
python -m src.quantbuild.app --config configs/xauusd.yaml backtest --days 30

# Run tests
pytest tests/ -v
```

## Architecture

```
src/quantbuild/
├── models/           Pydantic typed models (Trade, Signal, NewsEvent, Config)
├── strategy_modules/ ICT modules (sweep, FVG, displacement, OB, MSS, structure)
├── strategies/       SQE 3-pillar entry model
├── backtest/         Bar-by-bar backtest engine with metrics
├── news/             Real-time news pipeline (RSS, NewsAPI, LLM sentiment)
├── execution/        Oanda v20 broker, order manager, position monitor
├── alerts/           Telegram trade/news/daily alerts
├── dashboard/        Streamlit web dashboard
├── data/             Session logic, data schemas
├── indicators/       ATR, EMA, swing detection
└── io/               Parquet loader, Oanda price feed
```

## Strategy: SQE (Smart Quality Entry)

Three-pillar ICT model:
1. **Trend context** — market structure shift + displacement
2. **Liquidity levels** — liquidity sweep + fair value gaps
3. **Entry trigger** — displacement confirmation

Only trades in confirmed structure (HH/HL for longs, LH/LL for shorts).

## News Layer

Real-time news pipeline ported from Polymarket news bot:
- RSS feeds (Kitco, Reuters, Bloomberg, Fed)
- NewsAPI (optional)
- Gold-specific event classifier
- LLM/rule-based sentiment (hybrid mode)
- Counter-news detection on open positions
