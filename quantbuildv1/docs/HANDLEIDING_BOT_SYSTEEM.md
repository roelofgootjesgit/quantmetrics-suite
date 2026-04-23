# Handleiding: Een Algoritmisch Trading Bot Systeem Bouwen

> Gebaseerd op het Quantbuild E1 v1 project — een volledig ICT-gebaseerd XAUUSD trading systeem
> met backtesting, real-time nieuws, live executie en geautomatiseerde alerts.

---

## Inhoudsopgave

1. [Filosofie en uitgangspunten](#1-filosofie-en-uitgangspunten)
2. [Projectstructuur opzetten](#2-projectstructuur-opzetten)
3. [Fase 1 — Fundament: Models en configuratie](#3-fase-1--fundament-models-en-configuratie)
4. [Fase 2 — Strategie-modules bouwen](#4-fase-2--strategie-modules-bouwen)
5. [Fase 3 — Backtest engine](#5-fase-3--backtest-engine)
6. [Fase 4 — Nieuwspipeline](#6-fase-4--nieuwspipeline)
7. [Fase 5 — Live executie](#7-fase-5--live-executie)
8. [Fase 6 — Alerts en monitoring](#8-fase-6--alerts-en-monitoring)
9. [Fase 7 — Research en optimalisatie](#9-fase-7--research-en-optimalisatie)
10. [Fase 8 — Productie-configuratie](#10-fase-8--productie-configuratie)
11. [Ontwikkelprincipes](#11-ontwikkelprincipes)
12. [Technologie-keuzes](#12-technologie-keuzes)
13. [Veelgemaakte fouten](#13-veelgemaakte-fouten)

---

## 1. Filosofie en uitgangspunten

### Config-driven development

Het belangrijkste principe: **alles wordt aangestuurd door configuratie, niet door hardcoded waarden**. Elke parameter — van TP/SL-ratio's tot nieuwsbronnen — staat in YAML-bestanden. Dit maakt het mogelijk om:

- Varianten te testen zonder code te wijzigen
- Productie-instellingen te scheiden van research-instellingen
- Snel te itereren op parameter-optimalisatie

### Modulair ontwerp

Elk onderdeel van het systeem is een zelfstandige module met een duidelijke interface. Modules weten niets van elkaar — ze communiceren via data (DataFrames, Pydantic models) en configuratie. Dit maakt het mogelijk om:

- Individuele modules te testen zonder het hele systeem
- Modules te vervangen zonder andere code te breken
- Geleidelijk complexiteit toe te voegen

### Gefaseerde ontwikkeling

Bouw het systeem in lagen: eerst de kern (models + backtest), dan signalen, dan nieuws, dan executie. Elke fase levert een werkend, testbaar product op. Spring niet vooruit — een backtest engine zonder goede models is waardeloos.

---

## 2. Projectstructuur opzetten

### Mappenstructuur

Begin met een heldere structuur die schaalt:

```
project/
├── configs/              # YAML configuratiebestanden
│   ├── default.yaml      # Basiswaarden (altijd geladen)
│   └── xauusd.yaml       # Instrument-specifiek profiel
│
├── scripts/              # Standalone tools en research scripts
│
├── src/projectnaam/      # Alle broncode
│   ├── __init__.py
│   ├── app.py            # CLI entrypoint
│   ├── config.py         # Config loader
│   │
│   ├── models/           # Pydantic datamodels
│   ├── strategy_modules/ # Indicator/signaal-modules
│   ├── strategies/       # Samengestelde strategieën
│   ├── backtest/         # Backtest engine + metrics
│   ├── news/             # Nieuwspipeline
│   ├── execution/        # Broker + order management
│   ├── alerts/           # Notificaties
│   ├── dashboard/        # Web UI
│   ├── data/             # Sessie-logica, schema's
│   └── io/               # Data laden/opslaan
│
├── tests/                # Unit tests
├── data/                 # Cache (git-ignored)
├── reports/              # Output van analyses (git-ignored)
│
├── .env.example          # Template voor secrets
├── .gitignore
├── requirements.txt
└── README.md
```

### Waarom deze structuur

| Map | Reden |
|-----|-------|
| `configs/` apart van `src/` | Config is geen code — het zijn instellingen die per omgeving verschillen |
| `scripts/` apart van `src/` | Research scripts zijn wegwerpbaar; core code niet |
| `models/` als eigen package | Models worden overal geïmporteerd — ze mogen geen circulaire dependencies hebben |
| `strategy_modules/` vs `strategies/` | Modules zijn bouwstenen (sweep, FVG); strategieën combineren die bouwstenen |

### Dependencies installeren

Maak een `requirements.txt` met expliciete minimum-versies:

```
pandas>=2.0
numpy>=1.24
pyyaml>=6.0
pyarrow>=12.0
python-dotenv>=1.0
pydantic>=2.0
feedparser>=6.0
httpx>=0.27
pytest>=7.0
pytest-cov
```

Optionele dependencies (commentaar tot je ze nodig hebt):

```
# openai            # LLM sentiment
# oandapyV20        # Live broker
# python-telegram-bot
# streamlit
```

### Environment setup

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt
cp .env.example .env            # Alleen lokaal: placeholders → echte waarden (gitignored)
```

Voor **QuantBuild E1** geldt: credentials horen in **`os.environ`**; een repo-`.env` is optionele dev-hulp (wordt door `python-dotenv` ingeladen). Canonieke namen en VPS/systemd: **`docs/CREDENTIALS_AND_ENVIRONMENT.md`** in de quantbuildv1-repo.

---

## 3. Fase 1 — Fundament: Models en configuratie

> **Doel**: Definieer alle datastructuren en de configuratielaag voordat je ook maar één regel logica schrijft.

### Stap 1: Pydantic models definieren

Begin met de kernvraag: **welke data stroomt door het systeem?** Definieer voor elk concept een strict getypeerd model.

#### Trade model

Het Trade model is het hart van het systeem. Het moet alles vastleggen wat je later wilt analyseren:

```python
from pydantic import BaseModel
from datetime import datetime
from typing import Optional

class Trade(BaseModel):
    timestamp: datetime
    direction: str              # "LONG" of "SHORT"
    entry_price: float
    exit_price: Optional[float] = None
    sl_price: float
    tp_price: float
    profit_r: float = 0.0       # Resultaat in R-multiples
    profit_usd: float = 0.0
    result: str = "OPEN"        # "WIN", "LOSS", "TIMEOUT"
    session: Optional[str] = None
    regime: Optional[str] = None
    modules_fired: list[str] = []
```

**Belangrijke keuze**: Meet winst in **R-multiples**, niet in dollars. Eén R = het bedrag dat je riskeert per trade. Dit maakt resultaten vergelijkbaar ongeacht positiegrootte.

#### Signal model

```python
class Signal(BaseModel):
    timestamp: datetime
    direction: str
    strength: str               # "STRONG", "MODERATE", "WEAK"
    modules_fired: list[str]
    news_boost: bool = False
    news_suppress: bool = False
```

#### Config schema

Gebruik Pydantic om je configuratie te valideren:

```python
class BacktestConfig(BaseModel):
    default_period_days: int = 60
    tp_r: float = 2.0
    sl_r: float = 1.0
    session_filter: list[str] = ["London", "New_York", "Overlap"]

class RiskConfig(BaseModel):
    max_position_pct: float = 0.02
    max_daily_loss_r: float = 3.0
    max_concurrent_positions: int = 2
    equity_kill_switch_pct: float = 10.0

class AppConfig(BaseModel):
    symbol: str
    timeframes: list[str]
    backtest: BacktestConfig
    risk: RiskConfig
    # ... meer secties
```

### Stap 2: Configuratiesysteem bouwen

Bouw een config loader die YAML-bestanden laadt met een **deep merge** strategie:

```python
import yaml
from pathlib import Path

def _deep_merge(base: dict, override: dict) -> dict:
    """Merge override into base zonder secties te overschrijven."""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result

def load_config(config_path: str = None) -> AppConfig:
    base = yaml.safe_load(Path("configs/default.yaml").read_text())

    if config_path:
        override = yaml.safe_load(Path(config_path).read_text())
        base = _deep_merge(base, override)

    return AppConfig(**base)
```

**Hiërarchie**: `default.yaml` → instrument YAML → productie YAML. Elke laag overschrijft alleen wat nodig is.

### Stap 3: Tests schrijven voor models

Test models **als eerste**. Als je models kloppen, klopt de rest makkelijker.

```python
class TestTrade:
    def test_create_winning_trade(self):
        trade = Trade(
            timestamp=datetime.now(),
            direction="LONG",
            entry_price=2000.0,
            exit_price=2020.0,
            sl_price=1990.0,
            tp_price=2020.0,
            profit_r=2.0,
            result="WIN",
        )
        assert trade.profit_r == 2.0
        assert trade.result == "WIN"
```

---

## 4. Fase 2 — Strategie-modules bouwen

> **Doel**: Bouw individuele signaal-modules die elk één ding detecteren. Combineer ze pas later tot een strategie.

### Stap 1: Base module definiëren

Maak een abstracte basisklasse waar alle modules van erven:

```python
from abc import ABC, abstractmethod
import pandas as pd

class BaseModule(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def calculate(self, data: pd.DataFrame, config: dict) -> pd.DataFrame:
        """Voeg signaalkolommen toe aan het DataFrame."""
        ...

    @abstractmethod
    def check_entry_condition(
        self, data: pd.DataFrame, index: int, config: dict, direction: str
    ) -> bool:
        """Check of de conditie geldig is op een specifieke bar."""
        ...
```

**Waarom een basisklasse?**
- Consistente interface — elke module werkt hetzelfde
- Testbaarheid — je kunt elke module onafhankelijk testen
- Compositie — strategieën combineren modules zonder hun interne werking te kennen

### Stap 2: Individuele modules implementeren

Elke module voegt kolommen toe aan het DataFrame. Voorbeeld van een Liquidity Sweep module:

```python
class LiquiditySweepModule(BaseModule):
    name = "liquidity_sweep"

    def calculate(self, data: pd.DataFrame, config: dict) -> pd.DataFrame:
        lookback = config.get("swing_lookback", 10)
        # Bereken swing highs en lows
        data["swing_high"] = data["high"].rolling(lookback, center=True).max()
        data["swing_low"] = data["low"].rolling(lookback, center=True).min()

        # Detecteer sweep: prijs breekt voorbij swing level en keert om
        data["bullish_sweep"] = (
            (data["low"] < data["swing_low"].shift(1))
            & (data["close"] > data["swing_low"].shift(1))
        )
        data["bearish_sweep"] = (
            (data["high"] > data["swing_high"].shift(1))
            & (data["close"] < data["swing_high"].shift(1))
        )
        return data
```

**In dit project bouwen we 8 ICT-modules**:

| Module | Detecteert | Kernlogica |
|--------|-----------|------------|
| Liquidity Sweep | Sweep van swing high/low + reversal | Prijs breekt swing level en keert terug |
| Displacement | Sterke beweging in één richting | 3+ candles met body >= 60% van range |
| Fair Value Gaps | Gaps tussen candles (inefficiency) | Candle 1 high < candle 3 low (of omgekeerd) |
| Market Structure Shift | Trendverandering | Breuk van swing high of swing low |
| Order Blocks | Institutionele zones | Laatste candle voor sterke reversal |
| Imbalance Zones | Wick-gebaseerde gaps | Significante gaps in prijsactie |
| Structure Context | Trend-identificatie | HH/HL = bullish, LH/LL = bearish |
| Structure Labels | Richting-filter | Blokkeert trades tegen de structuur in |

### Stap 3: Modules combineren tot een strategie

Maak een strategie die modules combineert met duidelijke logica:

```python
def run_sqe_conditions(data: pd.DataFrame, direction: str) -> pd.Series:
    """SQE (Smart Quality Entry) — 3-pijler model."""
    if direction == "LONG":
        # Pijler 1: Trend context (OR)
        trend = data["bullish_mss"] | data["bullish_disp"]
        # Pijler 2: Liquiditeit (AND met trend)
        liquidity = data["bullish_sweep"] & data["bullish_fvg"]
        # Pijler 3: Entry trigger
        trigger = data["bullish_disp"]
        # Structure filter
        structure = data["in_bullish_structure"]

        return trend & liquidity & trigger & structure

    # ... analoog voor SHORT
```

**Belangrijk**: Bereken alle modules één keer vooraf (`_compute_modules_once`) en pas dan de combinatie-logica toe. Dit voorkomt dubbel rekenwerk.

### Stap 4: Module-tests

Test elke module apart met synthetische data:

```python
def _make_ohlcv(n=50):
    """Creëer synthetisch OHLCV DataFrame voor tests."""
    dates = pd.date_range("2024-01-01", periods=n, freq="15min")
    return pd.DataFrame({
        "open": np.random.uniform(1990, 2010, n),
        "high": np.random.uniform(2000, 2020, n),
        "low": np.random.uniform(1980, 2000, n),
        "close": np.random.uniform(1990, 2010, n),
        "volume": np.random.randint(100, 1000, n),
    }, index=dates)

class TestLiquiditySweep:
    def test_calculate_adds_columns(self):
        module = LiquiditySweepModule()
        data = _make_ohlcv()
        result = module.calculate(data, {"swing_lookback": 10})
        assert "bullish_sweep" in result.columns
        assert "bearish_sweep" in result.columns
```

---

## 5. Fase 3 — Backtest engine

> **Doel**: Bouw een bar-by-bar simulator die trades uitvoert en metrics berekent.

### Stap 1: Data laden

Bouw een data-laag die meerdere bronnen ondersteunt met caching:

```python
def ensure_data(base_path: str, symbol: str, timeframe: str,
                start: datetime, end: datetime) -> pd.DataFrame:
    """Laad data: cache → Dukascopy → yfinance fallback."""
    cache_path = Path(base_path) / symbol / f"{timeframe}.parquet"

    if cache_path.exists():
        data = pd.read_parquet(cache_path)
        if data.index[-1] >= end:
            return data[(data.index >= start) & (data.index <= end)]

    # Probeer primaire bron, val terug op secundaire
    try:
        data = fetch_from_dukascopy(symbol, timeframe, start, end)
    except Exception:
        data = fetch_from_yfinance(symbol, timeframe, start, end)

    data.to_parquet(cache_path)
    return data
```

**Bewaar data als Parquet** — het is sneller dan CSV, kleiner, en behoudt datatypes.

### Stap 2: Sessie-logica

Trading is niet 24/7 gelijk. Definieer sessies:

```python
SESSIONS = {
    "London":  {"start": time(8, 0),  "end": time(12, 0)},
    "New_York": {"start": time(13, 0), "end": time(17, 0)},
    "Overlap": {"start": time(13, 0), "end": time(16, 0)},
    "Asia":    {"start": time(0, 0),  "end": time(8, 0)},
}

def session_from_timestamp(ts: datetime) -> str:
    """Bepaal in welke sessie een timestamp valt."""
    t = ts.time()
    for name, hours in SESSIONS.items():
        if hours["start"] <= t < hours["end"]:
            return name
    return "Off_Hours"
```

### Stap 3: Regime-detectie

Niet alle marktomstandigheden zijn gelijk. Classificeer het regime:

```python
class RegimeDetector:
    def detect(self, data: pd.DataFrame, config: dict) -> pd.Series:
        atr = data["high"].rolling(14).max() - data["low"].rolling(14).min()
        atr_ratio = atr / atr.rolling(50).mean()

        regime = pd.Series("TREND", index=data.index)
        regime[atr_ratio > 1.5] = "EXPANSION"
        regime[atr_ratio < 0.6] = "COMPRESSION"
        return regime
```

**Gebruik regime-profielen** om per regime andere instellingen te gebruiken:

```yaml
regime_profiles:
  TREND:
    skip: false
    tp_r: 2.0
    sl_r: 1.0
    allowed_sessions: [London, New_York, Overlap]
  EXPANSION:
    skip: false
    tp_r: 3.0       # Meer ruimte in volatiele markten
    sl_r: 1.5
    allowed_sessions: [New_York, Overlap]
  COMPRESSION:
    skip: true       # Niet traden in lage volatiliteit
```

### Stap 4: De backtest loop

De kern is een bar-by-bar loop:

```python
def run_backtest(cfg: AppConfig) -> list[Trade]:
    data = load_data(cfg)
    data = compute_all_modules(data, cfg.strategy)
    long_entries, short_entries = run_sqe_conditions(data)
    regime = RegimeDetector().detect(data, cfg.regime)

    trades = []
    equity = starting_equity
    peak_equity = equity
    daily_pnl = {}

    for i in range(len(data)):
        bar = data.iloc[i]
        session = session_from_timestamp(bar.name)

        # Risk checks
        if daily_pnl.get(bar.name.date(), 0) <= -cfg.risk.max_daily_loss_r:
            continue
        if (peak_equity - equity) / peak_equity >= cfg.risk.equity_kill_switch_pct / 100:
            continue

        # Regime check
        bar_regime = regime.iloc[i]
        profile = cfg.regime_profiles.get(bar_regime)
        if profile and profile.get("skip"):
            continue
        if session not in profile.get("allowed_sessions", []):
            continue

        # Entry check
        direction = None
        if long_entries.iloc[i]:
            direction = "LONG"
        elif short_entries.iloc[i]:
            direction = "SHORT"

        if direction is None:
            continue

        # Simuleer trade
        trade = simulate_trade(data, i, direction, profile)
        trades.append(trade)

        # Update tracking
        equity += trade.profit_usd
        peak_equity = max(peak_equity, equity)
        daily_pnl[bar.name.date()] = daily_pnl.get(bar.name.date(), 0) + trade.profit_r

    return trades
```

### Stap 5: Trade simulatie

Simuleer elke trade bar-by-bar vooruit:

```python
def simulate_trade(data: pd.DataFrame, entry_idx: int,
                   direction: str, profile: dict) -> Trade:
    entry_price = data.iloc[entry_idx]["close"]
    atr = compute_atr(data, entry_idx)

    if direction == "LONG":
        sl = entry_price - profile["sl_r"] * atr
        tp = entry_price + profile["tp_r"] * atr
    else:
        sl = entry_price + profile["sl_r"] * atr
        tp = entry_price - profile["tp_r"] * atr

    # Scan bars vooruit
    for j in range(entry_idx + 1, min(entry_idx + max_bars, len(data))):
        bar = data.iloc[j]
        if direction == "LONG":
            if bar["low"] <= sl:
                return Trade(..., result="LOSS", profit_r=-1.0)
            if bar["high"] >= tp:
                return Trade(..., result="WIN", profit_r=profile["tp_r"])
        # ... analoog voor SHORT

    return Trade(..., result="TIMEOUT", profit_r=0.0)
```

### Stap 6: Metrics berekenen

```python
def compute_metrics(trades: list[Trade]) -> dict:
    if not trades:
        return {}
    wins = [t for t in trades if t.result == "WIN"]
    losses = [t for t in trades if t.result == "LOSS"]

    total_r = sum(t.profit_r for t in trades)
    gross_profit = sum(t.profit_r for t in wins)
    gross_loss = abs(sum(t.profit_r for t in losses))

    return {
        "total_trades": len(trades),
        "win_rate": len(wins) / len(trades),
        "profit_factor": gross_profit / gross_loss if gross_loss > 0 else float("inf"),
        "expectancy_r": total_r / len(trades),
        "total_r": total_r,
        "max_drawdown_r": compute_max_drawdown(trades),
        "max_win_streak": compute_streak(trades, "WIN"),
        "max_loss_streak": compute_streak(trades, "LOSS"),
    }
```

**Bereken metrics ook per richting, regime en sessie** — dit onthult waar je strategie werkt en waar niet.

---

## 6. Fase 4 — Nieuwspipeline

> **Doel**: Bouw een real-time nieuwssysteem dat trading-beslissingen beïnvloedt.

### Architectuur

```
RSS Feeds ──┐                    ┌── Relevance Filter ── Gold Classifier
            ├── Normalizer ──────┤
NewsAPI ────┘   (dedup, hash)    └── Sentiment Engine ── News History
                                              │
                                        News Gate
                                    (blokkeert trades)
```

### Stap 1: Nieuwsbronnen

Definieer een basis-interface en implementeer bronnen:

```python
class NewsSource(ABC):
    @abstractmethod
    async def fetch(self) -> list[RawNewsItem]: ...

class RSSSource(NewsSource):
    def __init__(self, feeds: list[dict]):
        self.feeds = feeds  # [{"url": "...", "tier": 1}]

    async def fetch(self) -> list[RawNewsItem]:
        items = []
        for feed in self.feeds:
            parsed = feedparser.parse(feed["url"])
            for entry in parsed.entries:
                items.append(RawNewsItem(
                    headline=entry.title,
                    source=feed["url"],
                    tier=feed["tier"],
                    published=parse_date(entry.published),
                ))
        return items
```

### Stap 2: Normalisatie en deduplicatie

```python
class NewsNormalizer:
    def normalize(self, items: list[RawNewsItem]) -> list[NormalizedNewsEvent]:
        seen_hashes = set()
        events = []
        for item in items:
            content_hash = hashlib.md5(item.headline.encode()).hexdigest()
            if content_hash in seen_hashes:
                continue
            seen_hashes.add(content_hash)

            topics = self._extract_topics(item.headline)
            events.append(NormalizedNewsEvent(
                headline=item.headline,
                content_hash=content_hash,
                topics=topics,
                source_tier=item.tier,
                published=item.published,
            ))
        return events
```

### Stap 3: Relevance filtering

Niet elk nieuwsbericht is relevant. Score op basis van keywords en tijdsdecay:

```python
class RelevanceFilter:
    KEYWORD_SCORES = {
        "gold": 0.95, "xauusd": 0.95,
        "federal reserve": 0.85, "interest rate": 0.85,
        "inflation": 0.8, "dollar": 0.75,
    }

    def score(self, event: NormalizedNewsEvent) -> float:
        semantic = max(
            (score for kw, score in self.KEYWORD_SCORES.items()
             if kw in event.headline.lower()),
            default=0.3
        )
        hours_old = (datetime.now() - event.published).total_seconds() / 3600
        time_decay = max(0, 1 - hours_old / 24)

        return 0.7 * semantic + 0.3 * time_decay
```

### Stap 4: Sentiment engine

Bouw een hybride aanpak — rule-based als basis, LLM als upgrade:

```python
class HybridSentiment:
    def analyze(self, event: NormalizedNewsEvent) -> SentimentResult:
        try:
            return self._llm_sentiment(event)
        except Exception:
            return self._rule_based_sentiment(event)

    def _rule_based_sentiment(self, event: NormalizedNewsEvent) -> SentimentResult:
        headline = event.headline.lower()
        bullish_keywords = ["surges", "rallies", "safe haven", "rate cut"]
        bearish_keywords = ["drops", "falls", "rate hike", "strong dollar"]

        bull_score = sum(1 for kw in bullish_keywords if kw in headline)
        bear_score = sum(1 for kw in bearish_keywords if kw in headline)

        if bull_score > bear_score:
            return SentimentResult(direction="BULLISH", confidence=0.6)
        elif bear_score > bull_score:
            return SentimentResult(direction="BEARISH", confidence=0.6)
        return SentimentResult(direction="NEUTRAL", confidence=0.3)
```

### Stap 5: News Gate

De gate blokkeert trading rond high-impact events:

```python
class NewsGate:
    GATE_EVENTS = ["NFP", "FOMC", "CPI", "GDP", "Interest Rate", "Fed Chair"]
    BLOCK_BEFORE_MINUTES = 30
    BLOCK_AFTER_MINUTES = 15

    def check_gate(self, timestamp: datetime) -> tuple[bool, str]:
        """Return (allowed, reason)."""
        for event in self.recent_events:
            if event.classification in self.GATE_EVENTS:
                minutes_diff = (timestamp - event.published).total_seconds() / 60
                if -self.BLOCK_BEFORE_MINUTES <= minutes_diff <= self.BLOCK_AFTER_MINUTES:
                    return False, f"Geblokkeerd: {event.classification}"
        return True, ""
```

### Stap 6: Counter-news detectie

Bewaakt open posities tegen tegenstrijdig nieuws:

```python
class CounterNewsDetector:
    def check(self, position: Position, event: NormalizedNewsEvent) -> str:
        if position.direction == "LONG" and event.sentiment == "BEARISH":
            if event.source_tier == 1 and event.confidence > 0.8:
                return "exit"    # Sluit positie
            return "warn"        # Waarschuwing
        return "none"
```

---

## 7. Fase 5 — Live executie

> **Doel**: Vertaal backtested signalen naar echte orders bij een broker.

### Architectuur

```
┌──────────────────────────────────────────────┐
│                 Live Runner                    │
│                                               │
│  News Poller ──→ Gate Check                   │
│  Signal Check ──→ Risk Check ──→ Order Submit │
│  Position Monitor ──→ Counter-News ──→ Exit   │
│  Order Manager ──→ Break-even / Trail / Partial│
└──────────────────────────────────────────────┘
```

### Stap 1: Broker interface

Bouw een broker-wrapper die de API abstraheert:

```python
class OandaBroker:
    def __init__(self, account_id: str, token: str, practice: bool = True):
        self.client = oandapyV20.API(access_token=token, environment="practice")
        self.account_id = account_id

    def submit_market_order(self, instrument: str, units: int,
                            sl: float, tp: float) -> dict:
        order = MarketOrderRequest(
            instrument=instrument,
            units=units,
            stopLossOnFill=StopLossDetails(price=str(sl)),
            takeProfitOnFill=TakeProfitDetails(price=str(tp)),
        )
        return self.client.request(orders.OrderCreate(self.account_id, data=order.data))

    def get_current_price(self, instrument: str) -> tuple[float, float]:
        """Return (bid, ask)."""
        ...

    def close_trade(self, trade_id: str, units: int = None) -> dict:
        """Sluit (deel van) een trade."""
        ...
```

### Stap 2: Order Manager

Intelligent orderbeheer met drie mechanismen:

```python
class OrderManager:
    def update_price(self, trade_id: str, current_price: float):
        order = self.managed_orders[trade_id]

        # 1. Break-even: verplaats SL naar entry als winst > trigger
        if order.profit_r >= order.breakeven_trigger_r:
            new_sl = order.entry_price + order.breakeven_offset
            self.broker.modify_trade(trade_id, sl=new_sl)

        # 2. Partial close: sluit deel van positie
        if order.profit_r >= order.partial_trigger_r and not order.partial_done:
            close_units = int(order.units * order.partial_fraction)
            self.broker.close_trade(trade_id, units=close_units)
            order.partial_done = True

        # 3. Trailing stop: SL volgt prijs
        if order.profit_r >= order.trail_activation_r:
            trail_sl = current_price - order.trail_distance * order.atr
            if trail_sl > order.current_sl:
                self.broker.modify_trade(trade_id, sl=trail_sl)
```

**Sla state op naar JSON** voor crash recovery:

```python
def _save_state(self):
    state = {tid: order.dict() for tid, order in self.managed_orders.items()}
    Path("data/state.json").write_text(json.dumps(state))
```

### Stap 3: Position Monitor

```python
class PositionMonitor:
    def update_price(self, trade_id: str, price: float):
        pos = self.positions[trade_id]
        pos.current_price = price
        pos.peak_price = max(pos.peak_price, price)
        pos.unrealized_pnl = (price - pos.entry_price) * pos.units

    def invalidate_thesis(self, trade_id: str, reason: str):
        """Counter-news of marktverandering invalideert de positie."""
        pos = self.positions[trade_id]
        pos.thesis_valid = False
        pos.invalidation_reason = reason
```

### Stap 4: Live Runner — de hoofdloop

```python
class LiveRunner:
    def run(self):
        self.broker.connect()
        while True:
            # 1. Poll nieuws
            events = self.news_poller.poll()
            for event in events:
                self.news_gate.add_event(event)

            # 2. Counter-news check
            for pos in self.position_monitor.open_positions:
                for event in events:
                    action = self.counter_news.check(pos, event)
                    if action == "exit":
                        self.broker.close_trade(pos.trade_id)

            # 3. Signaal check (alleen in actieve sessies)
            session = session_from_timestamp(datetime.utcnow())
            if session in self.active_sessions:
                allowed, reason = self.news_gate.check_gate(datetime.utcnow())
                if allowed:
                    signal = self.check_signals()
                    if signal:
                        self.execute_signal(signal)

            # 4. Order management
            price = self.broker.get_current_price(self.instrument)
            for order in self.order_manager.active_orders:
                self.order_manager.update_price(order.trade_id, price)

            time.sleep(self.poll_interval)
```

---

## 8. Fase 6 — Alerts en monitoring

> **Doel**: Realtime inzicht in wat het systeem doet.

### Telegram alerts

Definieer formatters voor elk type bericht:

```python
def format_trade_entry(trade: Trade) -> str:
    emoji = "🟢" if trade.direction == "LONG" else "🔴"
    return (
        f"{emoji} **{trade.direction}** {trade.symbol}\n"
        f"Entry: {trade.entry_price:.2f}\n"
        f"SL: {trade.sl_price:.2f} | TP: {trade.tp_price:.2f}\n"
        f"R:R = 1:{trade.tp_r / trade.sl_r:.1f}\n"
        f"Modules: {', '.join(trade.modules_fired)}"
    )

def format_daily_summary(trades: list[Trade], equity: float) -> str:
    metrics = compute_metrics(trades)
    return (
        f"📊 **Daily Summary**\n"
        f"Trades: {metrics['total_trades']}\n"
        f"Win rate: {metrics['win_rate']:.0%}\n"
        f"Total R: {metrics['total_r']:+.1f}R\n"
        f"Equity: ${equity:,.2f}"
    )
```

**Alert types** die je wilt implementeren:

| Type | Wanneer | Inhoud |
|------|---------|--------|
| Trade Entry | Bij nieuwe order | Richting, levels, modules |
| Trade Exit | Bij sluiting | Resultaat, P&L, hold time |
| News Event | Bij relevant nieuws | Headline, sentiment, impact |
| Counter-News | Bij tegenstrijdig nieuws | Waarschuwing of exit |
| Daily Summary | Einde handelsdag | Metrics, equity |
| Error | Bij systeemfout | Foutmelding, context |

### Streamlit Dashboard

Vier tabbladen voor realtime monitoring:

```python
import streamlit as st

tab1, tab2, tab3, tab4 = st.tabs(["P&L", "Positions", "News", "Config"])

with tab1:
    st.line_chart(equity_curve)
    st.dataframe(trade_log)

with tab2:
    for pos in open_positions:
        st.metric(f"{pos.direction} {pos.symbol}", f"{pos.unrealized_pnl:+.2f}")

with tab3:
    for event in recent_news:
        st.write(f"**{event.headline}** — {event.sentiment}")

with tab4:
    st.json(active_config)
```

---

## 9. Fase 7 — Research en optimalisatie

> **Doel**: Gebruik data-gedreven analyse om de strategie te verbeteren.

### Research workflow

Dit is waar het echte werk zit. Bouw scripts die specifieke vragen beantwoorden:

#### 1. Variant-vergelijking

Vergelijk meerdere configuraties tegen dezelfde data:

```python
VARIANTS = {
    "BASELINE": "configs/xauusd.yaml",
    "PROD_V1": "configs/strict_prod_v1.yaml",
    "PROD_V2": "configs/strict_prod_v2.yaml",
}

results = {}
for name, config_path in VARIANTS.items():
    cfg = load_config(config_path)
    trades = run_backtest(cfg)
    results[name] = compute_metrics(trades)

# Vergelijk key metrics
for name, metrics in results.items():
    print(f"{name}: WR={metrics['win_rate']:.0%} PF={metrics['profit_factor']:.2f} "
          f"DD={metrics['max_drawdown_r']:.1f}R")
```

#### 2. Regime-analyse

Analyseer prestaties per marktregime:

- Regime-verdeling per jaar
- Metrics per regime (trend, expansion, compression)
- Regime × sessie kruistabel
- Expansion deep-dive (vroeg vs laat, London vs NY)

#### 3. Exit-strategie research

Test meerdere exit-methoden:

| Variant | Beschrijving |
|---------|-------------|
| Baseline | Vaste 2R TP |
| Partial + breakeven | 50% sluiten bij 1R, rest breakeven |
| ATR trailing | SL volgt op 2× ATR afstand |
| Expansion runner | 3R TP in expansion, 2R in trend |
| Hybrid 3-phase | Partial → breakeven → trail |

#### 4. A/B test: met en zonder nieuws

```python
# Run A: ICT-only
cfg_a = load_config("configs/xauusd.yaml")
cfg_a.news.gate_enabled = False
trades_a = run_backtest(cfg_a)

# Run B: ICT + nieuws
cfg_b = load_config("configs/xauusd.yaml")
trades_b = run_backtest(cfg_b)

# Vergelijk
print(f"ICT-only:  WR={compute_metrics(trades_a)['win_rate']:.0%}")
print(f"ICT+News:  WR={compute_metrics(trades_b)['win_rate']:.0%}")
```

#### 5. Monte Carlo simulatie

Test statistische robuustheid:

```python
def monte_carlo(trades: list[Trade], iterations: int = 500) -> dict:
    drawdowns = []
    for _ in range(iterations):
        shuffled = random.sample(trades, len(trades))
        equity_curve = list(accumulate(t.profit_r for t in shuffled))
        peak = 0
        max_dd = 0
        for eq in equity_curve:
            peak = max(peak, eq)
            max_dd = min(max_dd, eq - peak)
        drawdowns.append(abs(max_dd))

    return {
        "median_dd": np.median(drawdowns),
        "p95_dd": np.percentile(drawdowns, 95),
        "p99_dd": np.percentile(drawdowns, 99),
    }
```

### Sla resultaten op als JSON

Alle research-output gaat naar `reports/latest/*.json` — gestructureerd, vergelijkbaar, versioneerbaar.

---

## 10. Fase 8 — Productie-configuratie

> **Doel**: Van research naar een robuuste productie-setup.

### Config-hiërarchie

```
default.yaml          ← Basis (altijd geladen)
  └── xauusd.yaml     ← Instrument-profiel (research)
       └── strict_prod_v1.yaml  ← Eerste productie-versie
            └── strict_prod_v2.yaml  ← Geoptimaliseerde versie
```

### Van research naar productie

De reis van een research-config naar productie:

1. **Baseline** (`xauusd.yaml`): Alle parameters, breed bereik
2. **5-jaar backtest**: Test op maximale data (1825 dagen)
3. **Regime-analyse**: Ontdek welke regimes winst opleveren
4. **Prod v1** (`strict_prod_v1.yaml`): Skip compression, basisfilters
5. **Sessie-analyse**: Ontdek welke sessies per regime werken
6. **Prod v2** (`strict_prod_v2.yaml`): Sessie- en tijdfilters per regime

### Voorbeeld: Prod v2 optimalisaties

```yaml
regime_profiles:
  TREND:
    skip: false
    allowed_sessions: [London, New_York, Overlap]  # Geen Asia
    tp_r: 2.0
    sl_r: 1.0

  EXPANSION:
    skip: false
    allowed_sessions: [New_York, Overlap]           # Alleen NY sessies
    min_hour_utc: 10                                # Niet voor 10:00 UTC
    tp_r: 3.0
    sl_r: 1.5

  COMPRESSION:
    skip: true                                      # Niet traden
```

### Productie-checklist

- [ ] Backtest op minimaal 3-5 jaar data
- [ ] Monte Carlo: P95 drawdown acceptabel?
- [ ] Win rate > 40% (bij 2:1 R:R)
- [ ] Profit factor > 1.5
- [ ] Max drawdown < 25R
- [ ] Expectancy > 0.3R per trade
- [ ] Regime-profielen gevalideerd per sessie
- [ ] News gate getest met historische events
- [ ] Paper trading minimaal 2-4 weken stabiel
- [ ] Crash recovery getest (state.json)
- [ ] Telegram alerts werkend
- [ ] Kill switch getest (equity drawdown)

---

## 11. Ontwikkelprincipes

### Principe 1: Test-first voor models en modules

Schrijf tests voordat je logica bouwt. Tests definiëren het verwachte gedrag.

```
tests/
├── test_models.py        # Pydantic models, R:R berekening
├── test_ict_modules.py   # Individuele ICT modules
├── test_backtest.py      # Metrics, trade simulatie
└── test_news.py          # Normalisatie, relevance, sentiment, gate
```

### Principe 2: Synthetische data voor tests

Gebruik **nooit** echte marktdata in unit tests. Maak helpers die controleerbare data genereren.

### Principe 3: Config override, niet code wijzigen

Wil je iets anders testen? Maak een nieuw YAML-bestand. Wijzig geen code voor parameterveranderingen.

### Principe 4: Één module, één verantwoordelijkheid

- `LiquiditySweepModule` detecteert sweeps — niets anders
- `NewsGate` blokkeert trades — doet geen sentiment analyse
- `OrderManager` beheert orders — weet niets van signalen

### Principe 5: R-based risicomanagement

Meet alles in R-multiples. Dit maakt resultaten onafhankelijk van account-grootte en maakt vergelijkingen eerlijk.

### Principe 6: Gefaseerde validatie

```
Unit tests → Backtest → Regime-analyse → Monte Carlo → Paper trading → Live (klein) → Opschalen
```

Spring geen stappen over. Elk niveau vangt andere fouten.

---

## 12. Technologie-keuzes

| Component | Keuze | Waarom |
|-----------|-------|--------|
| **Taal** | Python 3.11+ | Ecosysteem voor data/finance |
| **Models** | Pydantic v2 | Strict typing + validatie + JSON serialisatie |
| **Data** | Pandas + PyArrow | Snelle Parquet I/O, vectorized berekeningen |
| **Config** | YAML + Pydantic | Leesbaar, valideerbaar, mergeable |
| **Marktdata** | Dukascopy + yfinance fallback | Gratis, betrouwbaar, meerdere timeframes |
| **Nieuws** | feedparser (RSS) + httpx | Lightweight, asynchrone HTTP |
| **Sentiment** | Rule-based + OpenAI GPT-4o-mini | Goedkoop + nauwkeurig, met fallback |
| **Broker** | Oanda v20 | Gratis paper account, goede API |
| **Alerts** | Telegram Bot API | Gratis, real-time, mobiel |
| **Dashboard** | Streamlit | Snel te bouwen, Python-native |
| **Testing** | pytest + pytest-cov | Standaard, krachtig, goede output |

---

## 13. Veelgemaakte fouten

### Fout 1: Te vroeg live gaan

**Probleem**: Je backtest ziet er goed uit, dus je gaat direct live met echt geld.

**Oplossing**: Doorloop de volledige validatie-pipeline. Paper trade minimaal 2-4 weken. Begin live met minimale positiegroottes.

### Fout 2: Overfitting op backtest data

**Probleem**: Je optimaliseert parameters tot de backtest perfect is — maar het werkt niet live.

**Oplossing**: Test altijd op out-of-sample data. Gebruik Monte Carlo om robuustheid te meten. Als het alleen werkt met hele specifieke parameters, is het overfit.

### Fout 3: Geen risk management

**Probleem**: Geen dagelijks verlies-limiet, geen equity kill switch, geen position sizing.

**Oplossing**: Implementeer vanaf dag 1:
- Max dagverlies (bijv. -3R)
- Equity kill switch (bijv. -10% van peak)
- Max concurrent posities
- Vaste R-risico per trade

### Fout 4: Hardcoded parameters

**Probleem**: SL op 10 pips, TP op 20 pips, overal in de code.

**Oplossing**: Elke parameter in config. ATR-gebaseerde levels in plaats van vaste pip-waarden (marktvolatiliteit verandert).

### Fout 5: Geen crash recovery

**Probleem**: Bot crasht, herstart, en weet niet meer welke posities open staan.

**Oplossing**: Sla state op (JSON/database). Bij herstart: laad state, synchroniseer met broker, hervat.

### Fout 6: Alle sessies gelijk behandelen

**Probleem**: Dezelfde strategie voor Asia (laag volume) als voor London/NY (hoog volume).

**Oplossing**: Analyseer prestaties per sessie. Gebruik sessie-filters en regime-profielen om alleen te traden waar het werkt.

### Fout 7: Nieuws negeren

**Probleem**: Je ICT-signaal is perfect, maar NFP komt over 5 minuten — je positie wordt uitgestopt door de spike.

**Oplossing**: Bouw een news gate die trading blokkeert rond high-impact events. Dit alleen al kan je drawdowns significant verlagen.

---

## Samenvatting: De bouwvolgorde

```
Week 1-2:  Models + Config + Tests
Week 3-4:  ICT Modules + Strategie
Week 5-6:  Backtest Engine + Metrics
Week 7-8:  Nieuwspipeline + Gate
Week 9-10: Live Executie + Order Management
Week 11:   Alerts + Dashboard
Week 12+:  Research, Optimalisatie, Productie-validatie
```

Elke fase bouwt voort op de vorige. Test continu. Gebruik configuratie om te experimenteren. Meet alles in R-multiples. En het allerbelangrijkste: **valideer met data, niet met gevoel**.

---

*Gebaseerd op Quantbuild E1 v1 — gebouwd als volledig ICT-gebaseerd XAUUSD trading systeem met 56 bronbestanden, 52 unit tests, en 6 ontwikkelfasen.*
