# EVENT_SCHEMA.md - QuantLog v1

## 1. Doel

Dit document definieert het canonieke event schema voor QuantLog v1.

Alle events uit QuantBuild en QuantBridge moeten dit schema gebruiken zodat:

- opslag uniform is
- replay mogelijk is
- metrics betrouwbaar zijn
- audits reproduceerbaar zijn

Principe: eerst een stabiel schema, daarna dashboards.

---

## 2. Canoniek event envelope

Elke event volgt dit formaat:

```json
{
  "event_id": "uuid",
  "event_type": "trade_action",
  "event_version": 1,
  "timestamp_utc": "2026-01-12T14:22:31.512Z",
  "ingested_at_utc": "2026-01-12T14:22:31.700Z",
  "source_system": "quantbuild",
  "source_component": "risk_engine",
  "environment": "paper",
  "run_id": "run_20260112_london_01",
  "session_id": "session_boot_abc",
  "source_seq": 18442,
  "trace_id": "trace_abc123",
  "order_ref": "ord_456",
  "position_id": "pos_789",
  "account_id": "paper_01",
  "strategy_id": "xauusd_ict_v3",
  "symbol": "XAUUSD",
  "severity": "info",
  "payload": {}
}
```

---

## 3. Envelope velden

| veld | verplicht | beschrijving |
|---|---|---|
| `event_id` | ja | unieke UUID |
| `event_type` | ja | event type |
| `event_version` | ja | schema versie |
| `timestamp_utc` | ja | brontijd van event |
| `ingested_at_utc` | ja | ingest tijd |
| `source_system` | ja | `quantbuild`, `quantbridge` of `quantlog` |
| `source_component` | ja | module/service naam |
| `environment` | ja | `paper`, `dry_run`, `live`, `shadow` |
| `run_id` | ja | unieke id voor 1 botrun |
| `session_id` | ja | unieke id voor boot/restart sessie |
| `source_seq` | ja | oplopende emitter-sequentie (>= 1) |
| `trace_id` | ja | volledige beslisketen |
| `order_ref` | nee | order lifecycle correlatie |
| `position_id` | nee | positie lifecycle correlatie |
| `account_id` | nee | account context |
| `strategy_id` | nee | strategie context |
| `symbol` | nee | instrument context |
| `severity` | ja | `info`, `warn`, `error`, `critical` |
| `payload` | ja | event specifieke velden |

---

## 4. Correlatieregels

Minimale correlatie-eisen:

- `trace_id` is altijd verplicht.
- `run_id` + `session_id` isoleren parallelle runs en restarts.
- `source_seq` moet oplopend zijn per emitter.
- Execution events gebruiken waar mogelijk `order_ref`.
- Position events gebruiken waar mogelijk `position_id`.
- Governance events bevatten `account_id`.

Zonder deze velden is betrouwbare replay niet mogelijk.

---

## 5. Event types (v1)

### QuantBuild

1. `signal_evaluated`
2. `risk_guard_decision`
3. `trade_action`
4. `adaptive_mode_transition`

### QuantBridge

5. `broker_connect`
6. `order_submitted`
7. `order_filled`
8. `order_rejected`
9. `governance_state_changed`
10. `failsafe_pause`

### QuantLog

11. `audit_gap_detected`

---

## 6. Payload voorbeelden per event type

### 6.1 `signal_evaluated`

```json
{
  "signal_type": "ict_sweep",
  "signal_direction": "LONG",
  "confidence": 0.62,
  "regime": "TREND",
  "news_state": "neutral",
  "spread": 18
}
```

### 6.2 `risk_guard_decision`

```json
{
  "guard_name": "spread_guard",
  "decision": "BLOCK",
  "reason": "spread_too_wide",
  "spread": 28,
  "max_allowed": 25
}
```

`decision` waarden: `ALLOW`, `BLOCK`, `REDUCE`, `DELAY`.

### 6.3 `trade_action`

```json
{
  "decision": "ENTER",
  "side": "BUY",
  "reason": "ict_sweep_london",
  "model_probability": 0.63,
  "market_probability": 0.55,
  "edge": 0.08,
  "risk_allowed": true,
  "position_size_r": 0.5,
  "expected_slippage": 0.10,
  "spread": 18
}
```

`decision` waarden: `ENTER`, `EXIT`, `REVERSE`, `NO_ACTION`.

Semantiek:

- `risk_guard_decision` bepaalt `ALLOW|BLOCK|REDUCE|DELAY`.
- `trade_action` geeft alleen trading intent weer (`ENTER|EXIT|REVERSE|NO_ACTION`).

### 6.4 `adaptive_mode_transition`

```json
{
  "old_mode": "BASE",
  "new_mode": "DEFENSIVE",
  "reason": "drawdown_threshold",
  "equity": 9845.0,
  "drawdown": 0.032
}
```

### 6.5 `broker_connect`

```json
{
  "broker": "ctrader",
  "environment": "paper",
  "status": "connected",
  "latency_ms": 120
}
```

### 6.6 `order_submitted`

```json
{
  "order_ref": "ord_456",
  "side": "BUY",
  "volume": 0.5,
  "order_type": "MARKET",
  "price_requested": 2351.30,
  "broker": "ctrader"
}
```

### 6.7 `order_filled`

```json
{
  "order_ref": "ord_456",
  "fill_price": 2351.42,
  "requested_price": 2351.30,
  "slippage": 0.12,
  "volume": 0.5,
  "broker": "ctrader"
}
```

### 6.8 `order_rejected`

```json
{
  "order_ref": "ord_456",
  "reason": "insufficient_margin",
  "broker_code": "MARGIN_001"
}
```

### 6.9 `governance_state_changed`

```json
{
  "account_id": "paper_01",
  "old_state": "normal",
  "new_state": "paused",
  "reason": "daily_dd_limit"
}
```

### 6.10 `failsafe_pause`

```json
{
  "reason": "spread_spike",
  "spread": 45,
  "duration_seconds": 300
}
```

### 6.11 `audit_gap_detected`

```json
{
  "source_system": "quantbuild",
  "gap_start_utc": "2026-03-29T18:00:05Z",
  "gap_end_utc": "2026-03-29T18:07:30Z",
  "gap_seconds": 445.0,
  "reason": "ingest_time_gap_exceeded_threshold"
}
```

---

## 7. Severity levels

| severity | betekenis |
|---|---|
| `info` | normaal event |
| `warn` | afwijking, maar systeem draait |
| `error` | fout die herstel vereist |
| `critical` | ernstige fout met trading impact |

---

## 8. Event naming rules

Gebruik consistente, leesbare namen:

- `signal_evaluated`
- `risk_guard_decision`
- `trade_action`
- `order_filled`
- `governance_state_changed`

Vermijd korte/ambigue namen zoals `filled` of `riskCheck`.

---

## 9. Minimale replay set voor een trade

Voor end-to-end replay van een trade zijn minimaal nodig:

1. `signal_evaluated`
2. `risk_guard_decision`
3. `trade_action`
4. `order_submitted`
5. `order_filled`

Optioneel/context:

- `governance_state_changed`
- `failsafe_pause`

---

## 10. Validatieregels voor v1

Een event is ongeldig als:

- verplichte envelope velden ontbreken
- `timestamp_utc` geen geldige UTC ISO timestamp is
- `environment` buiten toegestane set valt
- `severity` buiten toegestane set valt
- `run_id` of `session_id` leeg/ongeldig is
- `source_seq` geen positief getal is
- `trace_id` ontbreekt
- `payload` geen object is
- `trade_action.decision` buiten toegestane set valt
- `risk_guard_decision.decision` buiten toegestane set valt

Optioneel (warn-level):

- `ingested_at_utc` ligt voor `timestamp_utc`
- execution event zonder `order_ref`
- governance event zonder `account_id`

Replay-sorteerregel:

- primair op `timestamp_utc`
- secondair op `source_seq`
- tertiair op `ingested_at_utc`

---

## 11. Acceptatiecriteria

`EVENT_SCHEMA.md` is correct geimplementeerd wanneer:

- alle 11 v1 eventtypes valideerbaar zijn
- validator CLI invalid events markeert met duidelijke reden
- replay CLI op basis van correlatievelden werkt
- daily summary aantallen per eventtype kan rapporteren

