# QUANTANALYTICS_CONSUMER_PLAN.md

## Doel

Dit document definieert wat QuantAnalytics-Performance-Engine downstream doet met events uit QuantLog.

Doel:

QuantAnalytics zet ruwe events om in:

- reproduceerbare datasets
- deterministische metrics
- diagnostics
- feedback voor strategy improvement

---

# Scope

QuantAnalytics is strikt een **consumer layer**.

Wel:
- event ingestion
- normalization
- deterministic enrichment
- metric computation
- diagnostics
- reporting

Niet:
- order execution
- broker logic
- strategy decisioning
- event ownership
- realtime trading logic

---

# Core principle

QuantLog is de **source of truth**.

QuantAnalytics:

- leest events
- verandert ze niet
- voegt alleen afgeleide (deterministische) velden toe

---

# Input

Primair:

- QuantLog canonical events (JSONL)

Minimale eventtypes voor MVP:

- signal_detected
- signal_evaluated
- risk_guard_decision
- trade_action
- order_filled
- trade_closed

---

# Consumer pipeline

## 1. Ingestion

Lees events per:

- run_id
- date
- symbol
- strategy

Output:

→ raw events dataframe (append-only)

---

## 2. Normalization

Zet JSONL om naar platte tabellen.

### Canonical tables + grain

#### decisions (grain = 1 row per decision_cycle_id)

- decision_cycle_id
- timestamp
- symbol
- setup_type
- side
- session
- regime
- combo_count
- confidence
- final_decision (ENTER / NO_ACTION)
- reason
- blocking_layer
- blocking_guard_name

---

#### guard_decisions (grain = 1 row per guard verdict)

- decision_cycle_id
- guard_name
- decision
- reason
- threshold
- observed_value

---

#### executions (grain = 1 row per fill)

- trade_id
- order_ref
- symbol
- requested_price
- fill_price
- slippage
- fill_latency_ms
- spread_at_fill

---

#### closed_trades (grain = 1 row per closed trade)

- trade_id
- symbol
- side
- entry_time
- exit_time
- holding_time
- net_pnl
- r_multiple
- mae
- mfe
- exit_reason

---

## 3. Deterministic enrichment

Alle afgeleide velden moeten:

- volledig reproduceerbaar zijn
- alleen gebaseerd op eventdata

### Core derived fields

- signal_to_action_flag
- action_to_fill_flag
- fill_to_close_flag
- blocked_by_guard
- execution_cost
- realized_r
- mfe_capture_ratio
- mae_utilization
- holding_time_bucket
- session_bucket
- regime_bucket

GEEN subjectieve metrics toegestaan.

---

## 4. Analysis modules

---

## A. Throughput analysis (MVP)

Doel:
begrijpen waar de pipeline stopt

Metrics:

- signal_detected → signal_evaluated
- signal_evaluated → trade_action
- trade_action ENTER → order_filled
- filled → closed

- NO_ACTION distribution

Slices:

- per session
- per regime
- per setup_type
- per symbol

Output:

- funnel metrics
- drop-off points

---

## B. NO_ACTION diagnostics (MVP)

Doel:
verklaren waarom trades niet plaatsvinden

Metrics:

- count per NO_ACTION reason
- per session
- per regime
- per setup_type
- per symbol
- per run

Output:

- top blockers
- contextual breakdown

---

## C. Guard diagnostics (MVP)

Doel:
inzicht in guard gedrag

Metrics:

- blocks per guard
- block rate
- blocks per setup/session/regime

⚠️ Advanced metrics (NIET MVP):

- missed winner rate
- avoided loser rate
- Net Block Value

---

## D. Execution quality (requires QuantBridge support)

Doel:
meten wat execution kost

Metrics:

- gemiddelde slippage
- slippage distributie
- fill latency
- spread_at_fill
- execution_cost per trade

---

## E. Strategy performance (MVP)

Doel:
echte performance meten

Metrics:

- winrate
- avg pnl
- avg R
- expectancy
- profit factor
- drawdown

Slices:

- per setup_type
- per session
- per regime
- per combo_count
- per symbol

---

## F. Exit analysis (MVP light)

Doel:
begrijpen exit gedrag

Metrics:

- exit reason distribution
- MFE vs realized R
- MAE vs R
- holding time impact

---

# Output artifacts

## MVP outputs

- run_summary.json
- throughput_report.json
- no_action_breakdown.json
- strategy_slice_report.json

- trades.parquet
- decisions.parquet

## Human-readable (verplicht)

- run_summary.md

→ compacte interpretatie voor operator / AI

---

# Hard rules

- QuantLog = source of truth
- Geen mutatie van raw events
- Alle derived tables reproduceerbaar
- Geen business logic terug naar QuantLog
- Geen strategy tuning vóór datakwaliteit

---

# MVP consumer definition

MVP is klaar als:

1. events ingest worden
2. decisions table gebouwd is
3. closed trades table gebouwd is
4. throughput inzichtelijk is
5. NO_ACTION volledig verklaard kan worden
6. expectancy per setup/session/regime beschikbaar is

---

# Samenvatting

QuantAnalytics is de **research & diagnostics engine** van de stack.

Niet een dashboard.  
Niet een AI tool.  

Maar:

→ een deterministische engine die verklaart waar je edge zit en waar die verloren gaat.