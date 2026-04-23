# QUANTBUILD_DECISION_LOGGING_SPEC.md

## Doel

Dit document definieert het **logging contract** voor QuantBuild.

**Doel:** QuantBuild moet elke beslissing en niet-beslissing volledig **verklaarbaar** maken voor downstream analyse in QuantAnalytics (QuantAnalyze).

---

# Kernprincipe

```
Decision → Execution → QuantLog → QuantAnalyze → Improvement
```

QuantBuild is alleen verantwoordelijk voor:

- **decision logging**
- **execution logging**

**Niet** voor analyse.

---

# Belangrijkste regels

- Geen silent exits
- Elke cycle eindigt in **ENTER** of **NO_ACTION**
- Geen vrije tekst voor `reason` — alleen **canonical enums**
- Events zijn **append-only**
- Alles moet **replaybaar** zijn

---

# Event lifecycle

Volgorde (conceptueel):

1. `signal_detected`
2. `signal_evaluated`
3. `risk_guard_decision`
4. `trade_action`
5. `order_submitted`
6. `order_filled`
7. `trade_executed`
8. `trade_closed`

---

# `signal_evaluated` (VERPLICHT)

**Doel:** context van setup vastleggen.

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
  "atr": 12.5
}
```

---

# `risk_guard_decision` (VERPLICHT)

```json
{
  "guard_name": "spread_guard",
  "decision": "BLOCK",
  "reason": "spread_too_high",

  "threshold": 25,
  "observed_value": 31,

  "session": "london",
  "regime": "trend"
}
```

---

# `trade_action` (VERPLICHT)

## NO_ACTION

```json
{
  "decision": "NO_ACTION",
  "reason": "cooldown_active",

  "session": "new_york",
  "regime": "compression",
  "setup_type": "sqe"
}
```

## ENTER

```json
{
  "decision": "ENTER",
  "side": "BUY",

  "position_size_r": 0.5,
  "risk_allowed": true,

  "spread": 18
}
```

---

# `order_filled` (VERPLICHT)

```json
{
  "requested_price": 2351.30,
  "fill_price": 2351.42,

  "slippage": 0.12,
  "fill_latency_ms": 180,
  "spread_at_fill": 20
}
```

---

# `trade_closed` (VERPLICHT)

```json
{
  "exit_reason": "take_profit",

  "entry_time_utc": "...",
  "exit_time_utc": "...",

  "holding_time_seconds": 2100,

  "entry_price": 2351.42,
  "exit_price": 2356.80,

  "net_pnl": 88.1,
  "r_multiple": 1.8,

  "mae": -0.42,
  "mfe": 2.35
}
```

---

# Canonical enums

## NO_ACTION reasons

```
no_setup
regime_blocked
session_blocked
risk_blocked
spread_too_high
news_filter_active
cooldown_active
```

## Exit reasons

```
stop_loss
take_profit
trailing_stop
time_exit
signal_reverse
```

## Guard decisions

```
ALLOW
BLOCK
REDUCE
DELAY
```

---

# Decision cycle constraint

```
signal_evaluated
  → risk_guard_decision(s)
  → trade_action
```

Altijd eindigen in:

- **ENTER**, of
- **NO_ACTION**

---

# MVP scope

**Verplicht:**

- `signal_evaluated`
- `risk_guard_decision`
- `trade_action`
- `order_filled`
- `trade_closed`

---

# Samenvatting

QuantBuild produceert **deterministische, verklaarbare** event data voor QuantLog en downstream analytics.
