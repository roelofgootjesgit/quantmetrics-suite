# Quantbuild E1 v1 — XAUUSD Full-Stack Trading Bot

## Projectoverzicht

Een volledig ICT-gebaseerd trading systeem voor XAUUSD (goud), gebouwd in Python.
Het systeem combineert technische analyse (ICT Smart Money Concepts) met real-time
nieuwsanalyse, backtesting, live executie via Oanda en geautomatiseerde alerts.

---

## Wat is er gebouwd

### Architectuur

```
src/quantbuild/
├── models/              Pydantic typed models
├── strategy_modules/    ICT modules + news gate
│   └── ict/             8 ICT-concepten
├── strategies/          SQE entry strategie
├── backtest/            Bar-by-bar backtest engine
├── news/                Real-time news pipeline (10 modules)
├── execution/           Oanda broker + order management
├── alerts/              Telegram notificaties
├── dashboard/           Streamlit web dashboard
├── data/                Sessie-logica
└── io/                  Parquet data loader
```

**56 bronbestanden** | **52 unit tests** | **6 ontwikkelfasen**

---

### Fase 1 — Core: Models, ICT Modules, Backtest Engine

De fundering van het systeem. Alles is strict getypeerd met Pydantic v2 en
volledig configureerbaar via YAML.

#### Pydantic Models

| Model | Doel |
|-------|------|
| `Trade` | Volledige trade-registratie: entry/exit, SL/TP, P&L in USD en R, sessie, regime, nieuwscontext |
| `Signal` | Signaal met richting, sterkte (STRONG/MODERATE/WEAK), gefirde modules, nieuwsboost |
| `EntryCandidate` | Signal + berekende TP/SL/positiegrootte + blokkeerredenen |
| `Position` | Live positie met thesis-tracking, trailing stop, peak-price |
| `NormalizedNewsEvent` | Genormaliseerd nieuwsevent met dedup, source tier, topics |
| `SentimentResult` | Sentiment-analyse output: richting, confidence, impact op goud |
| `GoldEventClassification` | Goud-classificatie: niche, event type, impact snelheid |
| `AppConfig` | Root config die alle subconfiguraties composeert |

Alle config-parameters zijn gevalideerd met Pydantic validators (bereiken, types, enums).

#### ICT Modules (8 stuks)

Elke module erft van `BaseModule` en implementeert `calculate()` en `check_entry_condition()`.

| Module | Wat het detecteert | Output |
|--------|--------------------|--------|
| **Liquidity Sweep** | Prijs veegt swing high/low en reverst | `bullish_sweep`, `bearish_sweep` |
| **Displacement** | Sterke candles (body >= 60% van range) in serie | `bullish_disp`, `bearish_disp` |
| **Fair Value Gaps** | Gaps tussen candle 1 high en candle 3 low | `bullish_fvg`, `bearish_fvg`, zone-tracking |
| **Market Structure Shift** | High breekt boven swing high / low breekt onder swing low | `bullish_mss`, `bearish_mss` |
| **Order Blocks** | Bearish candle gevolgd door sterke up-move (en vice versa) | Zone-detectie met validity window |
| **Imbalance Zones** | Significante gaps tussen candles | Zone-tracking met validity |
| **Structure Context** | Pivot highs/lows → HH/HL vs LH/LL patronen | `structure_label` (BULLISH/BEARISH/RANGE) |
| **Structure Labels** | Trade-filtering op basis van structuur | Blokkeert RANGE, filtert richting |

#### SQE Strategie (Smart Quality Entry)

Drie-pijler ICT model:

```
┌─────────────────────────────────────────────────────┐
│                   SQE Entry Model                    │
├──────────────┬──────────────────┬────────────────────┤
│ Pillar 1     │ Pillar 2         │ Pillar 3           │
│ Trend Context│ Liquidity Levels │ Entry Trigger       │
├──────────────┼──────────────────┼────────────────────┤
│ MSS          │ Liquidity Sweep  │ Displacement        │
│ Displacement │ Fair Value Gaps  │                     │
│ (OR-logica)  │ (OR-logica)      │ (verplicht)         │
├──────────────┴──────────────────┴────────────────────┤
│ + Structure filter (alleen in bevestigde structuur)   │
│ + H1 gate (hogere tijdsframe structuurbevestiging)    │
│ + Sweep+Disp+FVG combo (min 2 van 3 in lookback)     │
└─────────────────────────────────────────────────────┘
```

#### Backtest Engine

- Bar-by-bar simulatie met ATR-gebaseerde TP/SL
- Sessie-filtering (London, New York, Overlap killzones)
- H1 structuurgate (hogere tijdsframe bevestiging)
- Automatische data-download via yfinance als fallback
- Risicobeheer: max positie %, max dagverlies, max concurrent posities

#### Metrics

| Metric | Beschrijving |
|--------|-------------|
| Win Rate | Percentage winnende trades |
| Profit Factor | Bruto winst / bruto verlies |
| Expectancy | Gemiddelde R per trade |
| Max Drawdown | Maximale R-drawdown |
| Splits | Per richting, regime, sessie |

---

### Fase 2 — News Layer: RSS, NewsAPI, Normalisatie, Filtering

Een volledige real-time nieuwspipeline, geport vanuit de Polymarket news bot.

```
RSS Feeds ──┐                    ┌── Relevance Filter ── Gold Classifier
            ├── Normalizer ──────┤
NewsAPI ────┘   (dedup, hash)    └── Sentiment Engine ── News History
```

#### Nieuwsbronnen

| Bron | Type | Tier |
|------|------|------|
| Kitco Gold | RSS | Tier 1 (primair) |
| Reuters Business | RSS | Tier 1 |
| Reuters World | RSS | Tier 2 |
| CNBC Economy | RSS | Tier 2 |
| Federal Reserve | RSS | Tier 1 |
| Bloomberg Markets | RSS | Tier 1 |
| NewsAPI | REST API | Configureerbaar |

#### Pipeline Modules

| Module | Functie |
|--------|---------|
| `NewsNormalizer` | MD5 headline-hashing voor dedup, topic-extractie (gold, macro, dollar, geopolitiek), betrouwbaarheidsscore per tier |
| `RelevanceFilter` | Gewogen score (70% semantisch + 30% tijdsdecay), goud-keywords scoren 0.95, macro 0.8, geopolitiek 0.7 |
| `GoldEventClassifier` | Classificeert events naar niche (gold/macro/dollar/geopolitiek), event type, impact-snelheid |
| `NewsPoller` | Combineert alle bronnen, pollt op interval, deduplicatie, gesorteerd op tijd |

---

### Fase 3 — News Gate, Sentiment Engine, Counter-News

De "intelligentie" laag die nieuws vertaalt naar trading-beslissingen.

#### News Gate

Blokkeert trading rond high-impact events:
- **30 min voor** en **15 min na** NFP, FOMC, CPI, GDP, Interest Rate, Fed Chair
- Sentiment boost: versterkt signalen bij sterk nieuwssentiment (> 0.7 confidence)
- Sentiment suppress: onderdrukt signalen bij tegenstrijdig sentiment (< 0.3)

#### Sentiment Engine (Hybride)

```
┌─────────────────────────────────────────┐
│           Hybrid Sentiment Mode          │
├─────────────────┬───────────────────────┤
│ Rule-Based      │ LLM (GPT-4o-mini)     │
│ Keyword matching│ JSON-gestructureerd    │
│ Snel, gratis    │ Nauwkeuriger, betaald  │
├─────────────────┴───────────────────────┤
│ Fallback: LLM faalt → rule-based        │
└─────────────────────────────────────────┘
```

- **Rule-based**: Bullish/bearish keyword sets met confidence scoring
- **LLM**: OpenAI API met JSON output (direction, confidence, impact_on_gold, reasoning)
- **Hybrid**: Probeert LLM, valt terug op rules bij failure

#### Counter-News Detectie

Bewaakt open posities tegen tegenstrijdig nieuws:
- Contradiction pairs: prijs, rente, geopolitiek
- Source tier bepaalt gewicht
- Acties: `exit` (boven threshold 0.8) of `warn`
- Invalideert positie-thesis bij exit-signaal

---

### Fase 4 — Live Executie: Oanda Broker, Order Management

Volledige live trading infrastructuur via Oanda v20 API.

#### Oanda Broker

| Functie | Beschrijving |
|---------|-------------|
| `get_account_info()` | Balance, NAV, margin, open trades |
| `get_current_price()` | Realtime bid/ask |
| `submit_market_order()` | Market order met SL/TP |
| `modify_trade()` | Wijzig SL/TP van open trade |
| `close_trade()` | Sluit specifieke trade |
| `stream_prices()` | Realtime prijsstream |

#### Order Manager

Intelligent orderbeheer met drie automatische mechanismen:

| Mechanisme | Trigger | Actie |
|-----------|---------|-------|
| **Break-even** | Trade bereikt trigger R | SL naar entry + offset |
| **Partial close** | Trade bereikt trigger R | Sluit % van positie |
| **Trailing stop** | Activatie R bereikt | SL volgt prijs op afstand |

State wordt opgeslagen naar JSON voor crash recovery.

#### Position Monitor

- Tracked alle open posities met thesis-validatie
- Prijs-updates en peak-tracking voor trailing
- Thesis-invalidatie door counter-news of marktverandering
- Summary output voor dashboard/alerts

#### Live Runner

Main event loop:
1. Connect naar broker
2. Poll nieuws op interval
3. News → relevance → classify → sentiment → gate check
4. Counter-news check tegen open posities
5. Signaal-check in actieve sessies (London/NY/Overlap)
6. Order executie en positie-monitoring

---

### Fase 5 — Telegram Alerts & Streamlit Dashboard

#### Telegram Bot

| Alert Type | Inhoud |
|-----------|--------|
| Trade Entry | Richting, entry, SL/TP, R:R, modules gefired |
| Trade Exit | Resultaat, P&L, holding time |
| News Event | Headline, sentiment, impact, bron |
| Counter-News | Waarschuwing of exit-advies |
| Daily Summary | Win rate, total R, posities, equity curve |
| Error | Systeem- of broker-fouten |

#### Streamlit Dashboard

Vier tabbladen:
- **P&L**: Equity curve, trade log, metrics
- **Positions**: Open posities met thesis status
- **News**: Laatste events, sentiment, relevance
- **Config**: Actieve configuratie

---

### Fase 6 — Historische Opslag, A/B Testing, News Collector

#### News History

- In-memory event + sentiment opslag
- Parquet export/import voor historische analyse
- JSON snapshot voor dashboard
- Tijdsbereik queries voor backtest-integratie

#### A/B Test Script

Vergelijkt twee strategiemodi:

| Run | Configuratie |
|-----|-------------|
| **A** | ICT-only (nieuws uitgeschakeld) |
| **B** | ICT + nieuws-laag ingeschakeld |

Output: vergelijkende metrics (win rate, PF, expectancy, drawdown) in JSON.

#### News Collector

Standalone script voor nieuwsverzameling:
- Configurable duur en interval
- Volledige pipeline: poll → filter → classify → sentiment
- Opslag naar Parquet + JSON

---

## Configuratie

Het systeem is volledig configureerbaar via `configs/xauusd.yaml`:

| Sectie | Parameters |
|--------|-----------|
| **Symbol** | XAUUSD, tijdsframes 15m + 1h |
| **Backtest** | 365 dagen, TP:R 2.0, SL:R 1.0 |
| **Risk** | Max 1.5% per positie, max -2.5R dagverlies, max 3 concurrent, equity kill switch 10% |
| **Strategy** | Alle 8 ICT modules met individuele parameters |
| **News** | 6 RSS feeds, relevance filtering, gate events, hybride sentiment |
| **Broker** | Oanda practice, XAU_USD, 1:100 leverage |
| **Monitoring** | Telegram + Dashboard (standaard uit) |
| **AI** | GPT-4o-mini, temp 0.2, 500 tokens |

---

## Testdekking

```
52 tests geslaagd — 0 failures

tests/test_backtest.py     6 tests   Metrics, trade simulatie, cache
tests/test_ict_modules.py  10 tests  Alle 8 ICT modules + structure
tests/test_models.py       14 tests  Trade, Signal, NewsEvent, Config, R:R
tests/test_news.py         22 tests  Normalizer, dedup, relevance, classifier,
                                     sentiment, gate, counter-news
```

---

## Technologie Stack

| Component | Technologie |
|-----------|------------|
| Taal | Python 3.11 |
| Models | Pydantic v2 |
| Data | Pandas, NumPy, PyArrow (Parquet) |
| Marktdata | yfinance |
| Nieuwsbronnen | feedparser (RSS), httpx (API) |
| Sentiment | Rule-based + OpenAI GPT-4o-mini |
| Broker | Oanda v20 (oandapyV20) |
| Alerts | Telegram Bot API (httpx) |
| Dashboard | Streamlit |
| Config | YAML + Pydantic validatie |
| Testing | pytest + pytest-cov |

---

## Roadmap — Wat komt er nog

### Korte termijn

- [ ] **Regime Detector** — Trend/range/volatility detectie (referenced in engine, nog niet geimplementeerd)
- [ ] **Signal wiring in LiveRunner** — `_check_signals()` stub koppelen aan SQE strategie
- [ ] **Indicators package** — ATR, EMA, swing detection (referenced in README, nog niet aangemaakt)
- [ ] **Backtest met nieuws** — Historisch nieuws integreren in backtest simulatie

### Middellange termijn

- [ ] **Multi-timeframe analyse** — H4/Daily structuur als extra filter
- [ ] **Walk-forward optimalisatie** — Parameter-optimalisatie met out-of-sample validatie
- [ ] **Monte Carlo simulatie** — Statistische significantie van backtest resultaten
- [ ] **Risk-adjusted metrics** — Sharpe ratio, Sortino, Calmar
- [ ] **Trade journaling** — Automatische trade-opslag met screenshots en context

### Lange termijn

- [ ] **Multi-instrument** — Uitbreiding naar andere paren (XAGUSD, indices)
- [ ] **ML-based signaalfiltering** — Feature engineering op ICT-signalen + ML classifier
- [ ] **Alternatieve brokers** — MetaTrader 5, Interactive Brokers
- [ ] **Cloud deployment** — Docker + VPS voor 24/7 operatie
- [ ] **Portfolio management** — Correlatie-bewuste positie-sizing over meerdere instrumenten

---

## Quick Start

```bash
# Omgeving opzetten
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env

# Tests draaien
pytest tests/ -v

# Data ophalen en backtesten
python -m src.quantbuild.app --config configs/xauusd.yaml fetch
python -m src.quantbuild.app --config configs/xauusd.yaml backtest --days 30

# Nieuws testen
python -m src.quantbuild.app --config configs/xauusd.yaml news-test

# Live trading (paper)
python -m src.quantbuild.app --config configs/xauusd.yaml live --dry-run
```
