QUANT_STACK_MVP_BLUEPRINT.md

## Doel

Dit document is het centrale entrypoint voor het bouwen van de Quant stack MVP.

Het beschrijft:

- wat we bouwen
- in welke volgorde
- welke documenten leidend zijn
- wanneer de MVP "klaar" is

---

# Wat we bouwen

We bouwen geen trading bot.

We bouwen een:

→ **deterministische trading decision & analysis machine**

De stack:

```text
Market Data
→ QuantBuild (Signal Engine)
→ QuantBridge (Execution Engine)
→ QuantLog (Observability Layer)
→ QuantAnalytics (Performance Engine)

Doel:

Decision → Execution → Logging → Analyse → Verbetering

Elke stap moet reproduceerbaar zijn.

Kernprincipe

De stack moet één ding perfect kunnen:

👉 verklaren waarom er wel of niet een trade is gedaan

Niet:

“we denken dat het werkt”
maar:

→ exact zien waar de pipeline stopt of winst maakt

De 4 kern documenten

Deze blueprint is gebaseerd op 4 specificaties:

1. Producer spec

👉 QUANTBUILD_EVENT_PRODUCER_SPEC.md

Definieert:

decision chain
signal context
guard context
trade_action

Belangrijk:

→ elke evaluatie = één decision cycle
→ geen silent exits
→ alles gekoppeld via decision_cycle_id

2. Consumer plan

👉 QUANTANALYTICS_CONSUMER_PLAN.md

Definieert:

hoe events worden omgezet naar datasets
welke metrics we berekenen
hoe diagnostics werken

Belangrijk:

→ QuantLog = source of truth
→ alleen deterministic enrichment
→ geen business logic

3. Implementation sequence

👉 QUANT_STACK_IMPLEMENTATION_SEQUENCE.md

Definieert:

exacte bouwvolgorde
1. producer correctness
2. execution correctness
3. validation
4. analytics
5. strategy tuning

Belangrijk:

→ volgorde niet veranderen

4. Canonical IDs & grains

👉 QUANT_STACK_CANONICAL_IDS_AND_GRAINS.md

Definieert:

alle identifiers
hoe events gekoppeld worden
wat elke dataset rij betekent

Belangrijk:

→ zonder dit = geen betrouwbare analyse

Bouwvolgorde (operationeel)
FASE 1 — QuantBuild correct krijgen

Doel:

→ volledige decision trace

Checklist:

decision_cycle_id aanwezig
signal_detected → evaluated → guard → action
altijd trade_action (ENTER of NO_ACTION)
canonical NO_ACTION reasons
signal context compleet
FASE 2 — QuantBridge correct krijgen

Doel:

→ volledige trade lifecycle

Checklist:

trade_id aanwezig
order_ref aanwezig
order_filled bevat slippage + latency
trade_closed bevat:
pnl
R
MAE
MFE
holding time
FASE 3 — QuantLog validatie

Doel:

→ data betrouwbaar maken

Controleer:

geen missende events
geen orphan records
correcte volgorde
correcte IDs
geen lege critical fields
FASE 4 — QuantAnalytics MVP

Doel:

→ eerste echte inzichten

Bouw:

decisions table (per cycle)
trades table (per trade)

Metrics:

throughput funnel
NO_ACTION breakdown
expectancy per:
setup
session
regime

Output:

run_summary.json
run_summary.md
FASE 5 — Strategy iteration

Pas nu:

thresholds
filters
execution settings

Niet:

alles tegelijk veranderen

Wel:

1 wijziging → nieuwe run → vergelijken
MVP Definition of Done

De MVP is klaar als:

1. Decision trace klopt

Voor elke cycle:

signal_detected
signal_evaluated
risk_guard_decision(s)
trade_action
2. Trade lifecycle klopt

Voor elke trade:

trade_action (ENTER)
order events
trade_closed
3. Data is valide
geen ontbrekende IDs
geen broken chains
geen inconsistente events
4. Analytics werkt

Je kunt beantwoorden:

waarom trades niet gebeuren
waar pipeline stopt
welke setups werken
waar edge verloren gaat
5. Reproduceerbaarheid

Een volledige run kan:

→ opnieuw geanalyseerd worden
→ met exact dezelfde uitkomst