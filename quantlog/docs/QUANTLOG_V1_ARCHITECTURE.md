# QuantLog v1 - Architecture and MVP Definition

## 1. Doel van QuantLog

QuantLog is de centrale logging-, audit-, replay- en metricslaag van de QuantBuild trading stack.

Kerncapability:

> Elke trade, block, guard decision en order moet end-to-end reproduceerbaar zijn.

QuantLog is geen gewone logger, maar de event spine van het trading operating system.

Belangrijke vragen die QuantLog moet beantwoorden:

- Waarom werd een trade genomen of geblokkeerd?
- Welke risk guard bepaalde de uitkomst?
- Welke account/policy was actief?
- Wat gebeurde er bij broker-executie?
- Waar kwam slippage of reject vandaan?

---

## 2. Rol in de architectuur

```text
Market Data / News
        |
Signal Engine
        |
Probability / Edge
        |
Risk Engine
        |
Execution Engine (QuantBridge)
        |
Broker

All decisions and execution events
                |
             QuantLog
                |
        Replay / Metrics / Audit
```

QuantLog zit naast de trading pipeline als observability- en auditlaag.

Hard ontwerpprincipe:

- Trading is fail-open op loggingproblemen.
- Audit is fail-closed (audit gaps moeten expliciet gemarkeerd worden).

---

## 3. Kernontwerp: Event Spine v1

QuantLog v1 start klein en hard:

- Event ingest
- Validatie
- Append-only opslag
- Replay per trace/trade
- Basale daily summary
- Ingest health check + `audit_gap_detected` event

```text
QuantBuild ----\
                \
                 -> Ingest -> Validate -> Append-Only Store -> Replay
                /
QuantBridge ---/

                                  -> Daily Summary
                                  -> Basic Metrics
```

---

## 4. Canoniek event envelope schema

Alle events gebruiken dezelfde basisstructuur:

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

Verplicht in v1:

- `event_id`
- `event_type`
- `event_version`
- `timestamp_utc`
- `ingested_at_utc`
- `source_system`
- `environment`
- `run_id`
- `session_id`
- `source_seq`
- `trace_id`
- `severity`
- `payload`

Correlatievelden:

- `trace_id` (decision chain)
- `order_ref` (order lifecycle)
- `position_id` (position lifecycle)
- `account_id` (governance)
- `strategy_id` (strategy context)
- `run_id` + `session_id` (runtime isolation)
- `source_seq` (stable event ordering per emitter)

Semantische scheiding:

- `risk_guard_decision` gebruikt `ALLOW|BLOCK|REDUCE|DELAY`.
- `trade_action` gebruikt `ENTER|EXIT|REVERSE|NO_ACTION`.

---

## 5. Event types voor v1 (minimale set)

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

## 6. Opslagmodel (JSONL-first)

V1 is append-only JSONL per dag en per source:

```text
data/events/
  2026-01-12/
    quantbuild.jsonl
    quantbridge.jsonl
```

Waarom JSONL-first:

- simpel en robuust
- append-only zonder databasecomplexiteit
- makkelijk te parsen/replayen
- later te materialiseren naar Parquet

---

## 7. Replay engine (belangrijkste feature)

Eerste prioriteit:

```bash
python -m quantlog.cli replay-trace --trace-id <TRACE_ID>
```

Gewenste output:

```text
14:22:30 signal_evaluated -> LONG bias
14:22:31 risk_guard_decision -> ALLOW
14:22:31 trade_action -> ENTER BUY
14:22:31 order_submitted -> broker=oanda
14:22:31 order_filled -> fill=2351.42
14:30:12 governance_state_changed -> state=normal
```

Als dit werkt, is QuantLog v1 functioneel waardevol.

Replay sorting rule:

1. `timestamp_utc`
2. `source_seq`
3. `ingested_at_utc`

---

## 8. Daily summary metrics (v1)

Per dag minimaal:

- events ingested
- invalid events
- trades attempted
- trades filled
- blocks by reason
- broker rejects
- failsafe pauses
- ingest success ratio

Execution metrics in v1:

- fill/submitted ratio
- reject rate
- mean/median slippage
- spread rejection rate (indien beschikbaar)

---

## 9. MVP implementatievolgorde

1. Definieer canoniek envelope-schema en 11 eventtypes.
2. Bouw JSONL emitters in QuantBuild en QuantBridge.
3. Bouw validator CLI (required fields, timestamps, severity, correlation).
4. Bouw replay CLI (`replay-trace`).
5. Bouw dagelijkse summary generator.
6. Voeg pas daarna uitgebreidere KPI's toe (NBV, adaptive/static delta).

---

## 10. Folderstructuur voorstel

```text
quantlog-v1/
├── configs/
├── docs/
├── scripts/
├── src/quantlog/
│   ├── events/
│   ├── ingest/
│   ├── validate/
│   ├── store/
│   ├── replay/
│   ├── summarize/
│   └── cli/
├── tests/
└── data/events/
```

---

## 11. Harde architectuurregels

1. Append-only events; geen mutatie.
2. Schema versioning verplicht (`event_version`).
3. UTC-only timestamps.
4. Idempotente ingest.
5. Trading mag niet blokkeren door logging.
6. Audit gaps moeten expliciet als event gelogd worden.
7. Elke block decision moet een reason hebben.
8. Elke trade moet replaybaar zijn via correlatievelden.
9. Elk event bevat `environment`, `run_id`, `session_id`.
10. Elke emitter houdt oplopende `source_seq` bij.
11. Lifecyclevoorbeelden gebruiken alleen eventtypes uit de schema registry.
12. `trade_action` en `risk_guard_decision` overlappen semantisch niet.

---

## 12. Definitie: "QuantLog v1 production ready"

QuantLog v1 is klaar wanneer:

- QuantBuild beslissingen als canonieke events landen.
- QuantBridge order lifecycle als canonieke events landt.
- `replay-trace` end-to-end werkt voor echte traces.
- Daily summary automatisch draait.
- Execution baseline metrics zichtbaar zijn.
- Governance state transitions tracebaar zijn.
- Event store append-only en immutable werkt in praktijk.

Dan is QuantLog geen nice-to-have logger, maar een echte trading black box recorder.

