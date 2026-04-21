# QUANT_STACK_IMPLEMENTATION_SEQUENCE.md

## Doel

Dit document beschrijft de bouwvolgorde over de echte Quant stack:

- QuantBuild-Signal-Engine
- QuantBridge-Execution-Engine
- QuantLog-Observability-Layer
- QuantAnalytics-Performance-Engine
- QuantOS-Orchestrator

Doel:

eerst correcte data,
daarna betrouwbare analyse,
pas daarna strategy changes.

---

# FASE 1 — Event correctness in producers

## Stap 1
Fix run_id en session_id consistentie over de stack.

## Stap 2
Forceer in QuantBuild:
signal_evaluated → trade_action
zonder silent exit.

## Stap 3
Implementeer canonical NO_ACTION reasons.

## Stap 4
Breid signal_evaluated uit met minimale context:
- session
- regime
- setup_type
- combo_count
- confidence
- price_at_signal
- spread

## Stap 5
Breid risk_guard_decision uit met:
- guard_name
- decision
- reason
- threshold
- observed_value

Deliverable fase 1:
betrouwbare decision chain in QuantLog.

---

# FASE 2 — Execution correctness

## Stap 6
Breid vanuit QuantBridge order_filled uit met:
- requested_price
- fill_price
- slippage
- fill_latency_ms
- spread_at_fill

## Stap 7
Zorg dat trade_executed en trade_closed lifecycle-consistent zijn.

## Stap 8
Breid trade_closed uit met:
- exit_reason
- entry_time_utc
- exit_time_utc
- holding_time_seconds
- net_pnl
- r_multiple
- mae
- mfe

Deliverable fase 2:
betrouwbare execution + outcome chain.

---

# FASE 3 — QuantLog validation

## Stap 9
Draai minimaal 1 volledige run of 1 volledige handelsdag.

## Stap 10
Valideer:
- ontbrekende events
- inconsistent event order
- missende trade_closed
- missende fills
- enum violations
- lege critical fields

Deliverable fase 3:
bevestigde datakwaliteit.

---

# FASE 4 — QuantAnalytics MVP

## Stap 11
Bouw eerste dataset builder:
JSONL → normalized tables

Tabellen:
- decisions
- guard_decisions
- executions
- trades_closed

## Stap 12
Bouw eerste metrics:
- throughput funnel
- NO_ACTION distribution
- expectancy per setup/session/regime

Deliverable fase 4:
eerste bruikbare diagnostics-output.

---

# FASE 5 — Strategy improvement loop

## Stap 13
Identificeer bottlenecks:
- dominante NO_ACTION reasons
- guard overblocking
- execution edge loss
- slechte exit capture

## Stap 14
Pas pas daarna strategie-instellingen aan.

## Stap 15
Run opnieuw en vergelijk cross-run metrics.

Deliverable fase 5:
gesloten improvement loop.

---

# Niet doen

- geen strategy tuning vóór logging completeness
- geen dashboards vóór normalized datasets
- geen vrije tekst reasons
- geen business logic in QuantLog
- geen analyse-aannames zonder event coverage

---

# MVP definition of done

MVP is klaar als:

- QuantBuild een complete decision chain emit
- QuantBridge execution metrics emit
- QuantLog de chain volledig opslaat
- QuantAnalytics een throughput report en expectancy slices kan maken
- een volledige run reproduceerbaar geanalyseerd kan worden

---

# Samenvatting

Volgorde:

1. producer correctness
2. execution correctness
3. QuantLog validation
4. QuantAnalytics MVP
5. strategy iteration