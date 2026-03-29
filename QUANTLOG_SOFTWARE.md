# QuantLog v1 - Software Blueprint

## 1) Doel en positie in de suite

QuantLog is de centrale logging-, audit- en replay-laag binnen de QuantBuild Suite.

Waar QuantBuild beslissingen neemt (signal, regime, news gate, risk, execution) en QuantBridge orders uitvoert op brokerniveau, zorgt QuantLog voor:

- volledige decision trace (waarom een trade wel/niet is genomen)
- execution trace (wat er technisch bij broker/adapter is gebeurd)
- governance trace (welke account/risk policies actief waren)
- replaybare datasets voor analyse, debugging en validatie

Kort: QuantLog is de "zwarte doos" van het trading operating system.

---

## 2) Probleem dat QuantLog oplost

Zonder een dedicated logplatform ontstaan drie kritieke gaten:

1. Onvoldoende verklaarbaarheid  
   Je ziet PnL, maar niet altijd waarom beslissingen zijn genomen.

2. Moeizame foutanalyse  
   Crashes, guard-blocks of slippage-afwijkingen zijn lastig reproduceerbaar zonder consistente events.

3. Zwakke validatie tussen paper en live  
   Je kunt adaptive vs static, broker quality en policy-compliance niet hard vergelijken zonder uniforme eventdata.

QuantLog maakt van losse runtime logs een gestructureerde, querybare en replaybare observability-laag.

---

## 3) Scope van QuantLog v1

### In scope (v1)

- Event-inname uit QuantBuild en QuantBridge
- Uniform event-schema (JSONL-first)
- Eventvalidatie en normalisatie
- Immutable event-opslag (append-only)
- Basis replay en session timeline
- Dagelijkse samenvattingen en health-statistieken
- KPI's voor paper-acceptatie en micro-live gates

### Out of scope (v1)

- Full BI dashboard met complexe visual analytics
- Real-time stream processing op cluster-schaal
- Automatische parameter-optimalisatie

---

## 4) Integratie met bestaande systemen

## QuantBuild -> QuantLog

Belangrijke eventgroepen:

- `signal_evaluated`
- `regime_updated`
- `news_gate_decision`
- `risk_guard_decision`
- `adaptive_mode_transition`
- `trade_action` (TRADE / BLOCK / SKIP)
- `paper_shadow_comparison` (adaptive vs static)

## QuantBridge -> QuantLog

Belangrijke eventgroepen:

- `broker_connect`
- `account_selected`
- `order_submitted`
- `order_filled`
- `order_rejected`
- `position_synced`
- `failsafe_pause`
- `governance_state_changed`

## Correlatieprincipe

Alle events krijgen een gedeelde correlatieset:

- `trace_id` (beslisketen)
- `order_ref` (order lifecycle)
- `position_id` (positie lifecycle)
- `account_id` (governance/routing)
- `strategy_id` (kernel context)

Hierdoor kan 1 trade van signaal tot broker-close end-to-end gevolgd worden.

---

## 5) Kernarchitectuur

```text
QuantBuild events ----\
                       \
                        -> QuantLog Ingest API -> Validator -> Normalizer
                       /                                      |
QuantBridge events ---/                                       v
                                                      Append-Only Event Store
                                                              |
                                            +-----------------+-----------------+
                                            |                                   |
                                      Replay Engine                       Metrics Engine
                                            |                                   |
                                            v                                   v
                                   Incident/Decision Trace             Daily Ops Reports
```

### Componenten

1. Ingest API  
   Ontvangt events via file sink (JSONL), CLI of HTTP endpoint.

2. Validator  
   Controleert verplichte velden, eventtype-versie en timestamp-consistentie.

3. Normalizer  
   Harmoniseert veldnamen uit QuantBuild/QuantBridge naar 1 canoniek schema.

4. Event Store  
   Append-only JSONL per dag/session + optioneel Parquet voor snelle analyses.

5. Replay Engine  
   Bouwt een chronologische timeline per `trace_id`, `position_id` of `account_id`.

6. Metrics Engine  
   Berekent operationele en strategische KPI's (NBV, R/DD, guard rates, slippage drift).

---

## 6) Canoniek eventmodel (v1)

Minimale velden voor elk event:

- `event_id` (uuid)
- `event_type`
- `event_version`
- `timestamp_utc`
- `source_system` (`quantbuild` | `quantbridge`)
- `trace_id`
- `account_id` (indien van toepassing)
- `symbol` (indien van toepassing)
- `severity` (`info` | `warn` | `error`)
- `payload` (typed object)

Aanvullende typed payloads:

- Decision payload (regime/news/risk/adaptive info)
- Execution payload (broker response, fill/slippage/spread)
- Governance payload (account state, pause/breach reason)
- Shadow payload (adaptive_vs_static delta metrics)

---

## 7) Belangrijkste KPI's voor QuantLog

### Besliskwaliteit

- Net Block Value (NBV) = avoided_loser_R - missed_winner_R
- Adaptive R/DD vs Static R/DD
- Missed winner rate
- Block reason distribution

### Execution quality

- Gemiddelde slippage per instrument
- Spread rejection rate
- Fill quality trend (drift detectie)
- Runtime failsafe rate

### Governance/compliance

- Aantal policy breaches geblokkeerd
- Paused/breached account respect ratio (moet 100% zijn)
- Deterministische account-selectie conform policy

### Operationele stabiliteit

- Runtime uptime
- Crash-free interval
- Event-ingest success rate
- Log rotatie en archief-integriteit

---

## 8) Folderstructuur voorstel (QuantLog repo)

```text
quantLog-v1/
├── configs/
│   ├── quantlog.default.yaml
│   ├── schema_registry.yaml
│   └── retention.yaml
├── docs/
│   ├── EVENT_SCHEMA.md
│   ├── REPLAY_RUNBOOK.md
│   └── OPS_CHECKLIST.md
├── scripts/
│   ├── ingest_events.py
│   ├── validate_events.py
│   ├── replay_trace.py
│   ├── summarize_day.py
│   └── rotate_logs.py
├── src/quantlog/
│   ├── ingest/
│   ├── schema/
│   ├── normalize/
│   ├── store/
│   ├── replay/
│   ├── metrics/
│   └── cli/
├── tests/
│   ├── test_schema_validation.py
│   ├── test_normalization.py
│   ├── test_replay.py
│   └── test_metrics.py
└── logs/
```

---

## 9) MVP Roadmap (realistisch en direct bruikbaar)

### Fase 1 - Foundation (week 1-2)

- Canoniek schema v1 vastleggen
- JSONL ingest + validatie pipeline
- Basis CLI: `ingest`, `validate`, `summarize`

### Fase 2 - Cross-system trace (week 3-4)

- QuantBuild event adapters
- QuantBridge event adapters
- Correlatie op `trace_id/order_ref/position_id`

### Fase 3 - Replay en paper gates (week 5-6)

- Replay per trace/account/symbol
- Gate reports (30/50/100 trades)
- NBV + adaptive/static vergelijkingen automatisch rapporteren

### Fase 4 - Ops hardening (week 7-8)

- Rotatie/retentie
- Fouttolerantie en dead-letter queue
- Dagelijkse health checks en alerts

---

## 10) Productieprincipes voor QuantLog

1. Append-only en immutable events  
   Nooit achteraf events herschrijven.

2. Schema-versioning verplicht  
   Elke eventwijziging met `event_version`.

3. Idempotente ingest  
   Dubbele events moeten veilig genegeerd of gededupliceerd worden.

4. UTC-only timestamps  
   Geen lokale tijd in kernlogs.

5. Fail-open voor trading, fail-closed voor audits  
   Trading mag niet vastlopen door logging, maar audit gaps moeten expliciet gemarkeerd worden.

---

## 11) Concreet operationeel gebruik

QuantLog ondersteunt direct deze workflows:

- Incident analyse: "Waarom is trade X geblokkeerd?"
- Broker diagnose: "Waar kwam slippage drift vandaan?"
- Paper acceptatie: "Is adaptive live nog steeds beter dan static?"
- Governance audit: "Is account state machine correct afgedwongen?"
- Deployment go/no-go: "Zijn observability gates en runtime health stabiel?"

---

## 12) Definitie van "QuantLog v1 klaar"

QuantLog v1 is "production-ready" wanneer:

- alle kernbeslissingen uit QuantBuild als typed events landen
- alle order lifecycle events uit QuantBridge gecorreleerd zijn
- replay per trade end-to-end binnen minuten mogelijk is
- daily summaries automatisch gegenereerd worden
- paper acceptance metrics (NBV, R/DD, DD gates) reproduceerbaar zijn
- governance en execution afwijkingen direct zichtbaar zijn in logs/rapportage

Dan is QuantLog geen bijzaak, maar de centrale observability- en verbeterlaag van de volledige Quant-stack.

