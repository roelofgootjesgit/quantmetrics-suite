# QUANTLOG_STRATEGY_IMPROVEMENT_FIELDS.md

## Doel

Dit document definieert de **minimale en aanbevolen velden** die nodig zijn om QuantLog-data om te zetten van simpele logging naar een **research-grade dataset**.

Doel:

> Niet alleen weten wat er gebeurde, maar **waarom**, **in welke context**, en **met welk effect op edge**.

---

# 1. Kernprincipe

Elke trade en elke NO_ACTION moet later antwoord kunnen geven op:

* Was dit een goede setup?
* Welke filters blokkeerden?
* Wat kostte execution?
* Hoe goed was de exit?
* Waar zit de echte edge?

---

# 2. Event uitbreiding per type

---

## 2.1 signal_evaluated

**Doel:** markcontext + setup informatie

```json
{
  "setup_type": "sqe",
  "side": "LONG",
  "session": "london",
  "regime": "trend",
  "combo_count": 3,

  "sweep_detected": true,
  "displacement_detected": true,
  "fvg_detected": true,
  "market_structure_shift": true,

  "confidence": 0.74,

  "price_at_signal": 2351.30,
  "spread": 18,
  "atr": 12.5,

  "news_state": "neutral",
  "trend_context": "bullish",
  "liquidity_context": "above_equal_highs"
}
```

---

## 2.2 risk_guard_decision

**Doel:** begrijpen waarom trades geblokkeerd worden

```json
{
  "guard_name": "spread_guard",
  "decision": "BLOCK",
  "reason": "spread_too_high",

  "threshold": 25,
  "observed_value": 31,

  "session": "london",
  "regime": "trend",

  "pre_trade_risk": 0.012,
  "post_trade_risk_if_allowed": 0.018,

  "open_positions_count": 2,
  "portfolio_heat": 0.65
}
```

---

## 2.3 trade_action

**Doel:** centrale beslissingsuitkomst

### NO_ACTION

```json
{
  "decision": "NO_ACTION",
  "reason": "cooldown_active",

  "session": "new_york",
  "regime": "compression",
  "setup_type": "sqe"
}
```

### ENTER

```json
{
  "decision": "ENTER",
  "side": "BUY",

  "model_probability": 0.63,
  "market_probability": 0.55,
  "edge": 0.08,

  "risk_allowed": true,
  "position_size_r": 0.5,

  "expected_slippage": 0.10,
  "spread": 18
}
```

---

## 2.4 order_submitted

```json
{
  "order_ref": "ord_123",
  "side": "BUY",
  "volume": 0.50,

  "price_requested": 2351.30,
  "order_type": "MARKET",

  "expected_slippage": 0.10,
  "expected_spread": 18,

  "broker": "oanda"
}
```

---

## 2.5 order_filled

**Doel:** execution quality meten

```json
{
  "order_ref": "ord_123",

  "requested_price": 2351.30,
  "fill_price": 2351.42,

  "slippage": 0.12,
  "fill_latency_ms": 180,
  "spread_at_fill": 20,

  "partial_fill": false,
  "broker": "oanda"
}
```

---

## 2.6 trade_executed

```json
{
  "entry_price": 2351.42,
  "initial_sl": 2348.00,
  "initial_tp": 2358.00,

  "risk_r": 1.0,
  "position_size": 0.50,

  "effective_edge_after_fill": 0.05
}
```

---

## 2.7 trade_closed

**Doel:** outcome + exit kwaliteit

```json
{
  "exit_reason": "take_profit",

  "entry_time_utc": "2026-04-03T12:30:00Z",
  "exit_time_utc": "2026-04-03T13:05:00Z",

  "holding_time_seconds": 2100,

  "entry_price": 2351.42,
  "exit_price": 2356.80,

  "gross_pnl": 92.4,
  "net_pnl": 88.1,

  "r_multiple": 1.8,

  "mae": -0.42,
  "mfe": 2.35,
  "max_heat": 0.6,

  "session_at_entry": "london",
  "regime_at_entry": "trend"
}
```

---

# 3. Canonical NO_ACTION reasons

Gebruik exact deze strings:

```
no_setup
regime_blocked
session_blocked
risk_blocked
spread_too_high
news_filter_active
cooldown_active
```

Optioneel later:

```
position_limit_reached
confidence_too_low
duplicate_signal
execution_disabled
market_data_unavailable
```

---

# 4. Wat je hiermee kunt analyseren

## Throughput

* signal → action conversion
* action → fill conversion
* NO_ACTION distribution

## Strategy quality

* expectancy per setup_type
* expectancy per session
* expectancy per regime
* expectancy per combo_count

## Guard performance

* blocks per guard
* missed winner rate
* avoided loser rate
* Net Block Value

## Execution quality

* slippage distribution
* fill latency
* reject rate
* effective edge loss

## Exit performance

* exit reason distribution
* MFE vs gerealiseerde R
* MAE vs stop-loss
* holding time impact

---

# 5. Belangrijkste regel

> Elke trade en elke NO_ACTION moet later verklaarbaar zijn in context, oorzaak en resultaat.

Als je dat niet kunt beantwoorden met QuantLog → logging is onvoldoende.

---

# 6. Implementatie volgorde

## Fase 1 (nu)

* trade_closed uitbreiden
* order_filled uitbreiden
* signal_evaluated context uitbreiden
* NO_ACTION reasons volledig

## Fase 2

* guard attribution uitbreiden
* execution metrics verfijnen

## Fase 3

* dataset export (Parquet / DB)
* dashboards
* cross-run vergelijking

---

# Samenvatting

QuantLog moet evolueren van:

> “wat gebeurde er?”

naar:

> “waar zit de edge, waar verliezen we die, en hoe verbeteren we het systeem?”
