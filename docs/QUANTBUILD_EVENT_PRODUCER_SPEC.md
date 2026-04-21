# QUANT_STACK_IMPLEMENTATION_SEQUENCE.md

## Doel

Dit document definieert de exacte bouwvolgorde van de Quant stack:

- QuantBuild (Signal Engine)
- QuantBridge (Execution Engine)
- QuantLog (Observability Layer)
- QuantAnalytics (Performance Engine)
- QuantOS (Orchestrator)

Doel:

Eerst correcte en complete data  
→ daarna betrouwbare analyse  
→ pas daarna strategie-optimalisatie  

---

# Core principle

De stack wordt gebouwd in deze volgorde:

```text
Producer correctness
→ Execution correctness
→ Logging validation
→ Analytics
→ Strategy improvement

Geen stappen overslaan.

FASE 1 — Producer correctness (QuantBuild)

Doel:
een volledige en consistente decision chain produceren.

Stap 1 — Identifiers en correlatie

Introduceer verplichte keys:

run_id
session_id
decision_cycle_id (CRITISCH)

Alle QuantBuild events moeten deze bevatten.

Stap 2 — Decision chain afdwingen

Per evaluatiecyclus verplicht:

signal_detected
→ signal_evaluated
→ (0..n) risk_guard_decision
→ trade_action

Geen silent exits toegestaan.

Stap 3 — Canonical NO_ACTION reasons

Gebruik vaste enums:

no_setup
regime_blocked
session_blocked
risk_blocked
spread_too_high
news_filter_active
cooldown_active

Geen vrije tekst.

Stap 4 — Minimale signal context

signal_evaluated moet bevatten:

session
regime
setup_type
combo_count
confidence
price_at_signal
spread
Stap 5 — Guard context expliciet maken

risk_guard_decision moet bevatten:

guard_name
decision
reason
threshold
observed_value
Deliverable Fase 1
volledige decision trace per cycle
alle events gekoppeld via decision_cycle_id
geen ontbrekende trade_action events
FASE 2 — Execution correctness (QuantBridge)

Doel:
execution en outcome correct meetbaar maken.

Stap 6 — Execution metrics uitbreiden

order_filled moet bevatten:

trade_id
order_ref
requested_price
fill_price
slippage
fill_latency_ms
spread_at_fill
Stap 7 — Lifecycle consistentie

Zorg dat lifecycle compleet is:

trade_action (ENTER)
→ order_submitted
→ order_filled
→ trade_executed
→ trade_closed

Stap 8 — Trade outcome uitbreiden

trade_closed moet bevatten:

trade_id
entry_time_utc
exit_time_utc
holding_time_seconds
net_pnl
r_multiple
mae
mfe
exit_reason
Deliverable Fase 2
volledige trade lifecycle aanwezig
execution metrics beschikbaar
trades volledig reconstructeerbaar
FASE 3 — QuantLog validation

Doel:
datakwaliteit bevestigen vóór analyse.

Validatietypes
1. Schema validation
verplichte velden aanwezig
juiste datatypes
enums geldig
2. Sequence validation
correcte event volgorde
geen ontbrekende stappen in decision chain
geen incomplete trade lifecycle
3. Referential validation
trade_id consistent over events
decision_cycle_id consistent
order_ref correct gekoppeld
Stap 9 — Full run test

Draai:

minimaal 1 volledige handelsdag
of
1 volledige backtest run
Stap 10 — Validation checks

Controleer:

ontbrekende events
inconsistent event order
missende trade_closed
missende fills
lege critical fields
enum violations
orphan records (zonder referentie)
Deliverable Fase 3
gevalideerde dataset
geen kritieke datagaten
events volledig betrouwbaar voor analyse
FASE 4 — QuantAnalytics MVP

Doel:
eerste echte diagnostische inzichten bouwen.

Stap 11 — Dataset builder

Transformeer JSONL → tabellen:

decisions (1 row per decision_cycle_id)
guard_decisions (1 row per guard event)
executions (1 row per fill)
closed_trades (1 row per trade)
Stap 12 — Core metrics
Throughput funnel
signal_detected → evaluated
evaluated → action
action → fill
fill → close
NO_ACTION analyse
distribution per reason
per session
per regime
per setup
Strategy slices
expectancy per setup
expectancy per session
expectancy per regime
Deliverable Fase 4
eerste bruikbare diagnostics-output
inzicht waar pipeline faalt
inzicht waar edge zit
FASE 5 — Strategy improvement loop

Doel:
alleen nu strategie aanpassen.

Stap 13 — Bottleneck analyse

Identificeer:

dominante NO_ACTION reasons
overblocking guards
execution edge loss
slechte exit capture
lage throughput
Stap 14 — Controlled changes

Pas alleen aan:

thresholds
filters
execution settings

NIET alles tegelijk wijzigen.

Stap 15 — Cross-run vergelijking

Vergelijk runs op:

throughput
expectancy
drawdown
trade count
regime performance
Deliverable Fase 5
meetbare verbetering
reproduceerbare iteraties
gesloten feedback loop
Niet doen (critical)
geen strategy tuning vóór logging compleet is
geen dashboards vóór datasets correct zijn
geen vrije tekst reasons
geen business logic in QuantLog
geen analyse-aannames zonder data coverage
geen meerdere wijzigingen tegelijk zonder baseline
MVP definition of done

MVP is klaar als:

QuantBuild volledige decision chain emit
QuantBridge volledige execution chain emit
QuantLog alles correct opslaat
QuantAnalytics datasets + funnel + expectancy kan berekenen
1 volledige run reproduceerbaar geanalyseerd kan worden
Samenvatting

Volgorde:

producer correctness
execution correctness
QuantLog validation
QuantAnalytics MVP
strategy iteration

Afwijken van deze volgorde = gegarandeerd ruis en verkeerde conclusies.