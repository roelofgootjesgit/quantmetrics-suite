# QUANT_STACK_CANONICAL_IDS_AND_GRAINS.md

## Doel

Dit document definieert de canonical identifiers, referenties en dataset grains van de Quant stack.

Doel:

zorgen dat events uit QuantBuild, QuantBridge en QuantLog downstream in QuantAnalytics
betrouwbaar aan elkaar gekoppeld, gevalideerd en geanalyseerd kunnen worden.

---

# Core principle

Zonder stabiele identifiers bestaat er geen betrouwbare analyse.

De stack moet daarom werken met:

- vaste correlation keys
- duidelijke eigenaarschap per identifier
- expliciete referentieregels
- vaste dataset grains

---

# 1. Canonical identifiers

## 1.1 run_id

### Doel
Identificeert één volledige procesrun.

### Owner
QuantOS / stack runtime

### Verplicht op
- alle events

### Gebruik
- grouping per run
- replay
- per-run diagnostics
- cross-run vergelijking

---

## 1.2 session_id

### Doel
Identificeert één runtime sessie binnen een run of procescontext.

### Owner
QuantOS / runtime launcher

### Verplicht op
- alle events

### Gebruik
- onderscheiden van processen / sessies
- tracing binnen live runtime
- recovery / restart analyse

---

## 1.3 decision_cycle_id

### Doel
Identificeert één volledige decision cycle in QuantBuild.

### Owner
QuantBuild

### Verplicht op
- signal_detected
- signal_evaluated
- risk_guard_decision
- trade_action

### Gebruik
- koppelen van volledige decision chain
- throughput analysis
- NO_ACTION diagnostics
- guard diagnostics

### Hard rule
Elke decision cycle heeft exact één final trade_action.

---

## 1.4 trade_id

### Doel
Identificeert één trade lifecycle.

### Owner
QuantBuild / QuantBridge boundary  
(toegewezen zodra een ENTER leidt tot execution intent)

### Verplicht op
- trade_action (bij ENTER)
- order_submitted
- order_filled
- trade_executed
- trade_closed

### Gebruik
- lifecycle reconstructie
- execution analyse
- performance analyse
- exit analyse

### Hard rule
Elke closed trade moet exact één trade_id hebben.

---

## 1.5 order_ref

### Doel
Identificeert één order bij execution.

### Owner
QuantBridge

### Verplicht op
- order_submitted
- order_filled
- order_cancelled (later, indien gebruikt)
- order_rejected (later, indien gebruikt)

### Gebruik
- koppeling broker/order lifecycle
- partial fill analyse
- execution debugging

---

## 1.6 position_id

### Doel
Identificeert open broker/execution positie.

### Owner
Broker / QuantBridge local registry

### Verplicht op
- trade_executed
- trade_closed
- position update events (later)

### Gebruik
- positie-reconstructie
- sync/recovery
- broker reconciliation

---

## 1.7 symbol

### Doel
Identificeert het verhandelde instrument.

### Owner
Producer / execution layer

### Verplicht op
- alle marktgerelateerde events

### Hard rule
Gebruik één canonical symbol-formaat stack-breed.

Bijvoorbeeld:
- XAUUSD
- EURUSD
- NAS100

Geen mix van broker aliases in analytics-tabellen.

---

# 2. Referential rules

## 2.1 Decision chain

De volgende events moeten dezelfde keys delen:

- run_id
- session_id
- decision_cycle_id
- symbol

Chain:

signal_detected  
→ signal_evaluated  
→ risk_guard_decision (0..n)  
→ trade_action

---

## 2.2 Trade lifecycle

De volgende events moeten dezelfde keys delen:

- run_id
- session_id
- trade_id
- symbol

Lifecycle:

trade_action (ENTER)  
→ order_submitted  
→ order_filled  
→ trade_executed  
→ trade_closed

---

## 2.3 Decision-to-trade linkage

Als een decision cycle eindigt in ENTER, dan moet er een expliciete koppeling bestaan tussen:

- decision_cycle_id
- trade_id

### Hard rule
Een ENTER zonder trade_id is ongeldig voor downstream lifecycle analyse.

---

## 2.4 Order-to-trade linkage

Een order_ref moet altijd aan exact één trade_id gekoppeld zijn.

Meerdere fills mogen bestaan voor dezelfde trade_id indien partial fills ondersteund worden,
maar de referentie moet expliciet blijven.

---

# 3. Dataset grains

Dit deel definieert exact wat één rij betekent per tabel.

---

## 3.1 decisions table

### Grain
1 row per `decision_cycle_id`

### Doel
samenvatting van volledige decision cycle

### Typische keys
- run_id
- session_id
- decision_cycle_id
- symbol

### Hard rule
Elke decision_cycle_id komt exact één keer voor.

---

## 3.2 guard_decisions table

### Grain
1 row per guard verdict binnen een `decision_cycle_id`

### Doel
analyse van guard-gedrag

### Typische keys
- run_id
- session_id
- decision_cycle_id
- guard_name

### Hard rule
Meerdere guard rows per cycle toegestaan.

---

## 3.3 executions table

### Grain
1 row per fill event (`order_filled`)

### Doel
execution quality analyse

### Typische keys
- run_id
- session_id
- trade_id
- order_ref

### Hard rule
Meerdere rows per trade_id toegestaan als partial fills bestaan.

---

## 3.4 closed_trades table

### Grain
1 row per gesloten trade (`trade_id`)

### Doel
performance en exit analyse

### Typische keys
- run_id
- session_id
- trade_id
- symbol

### Hard rule
Elke trade_id komt maximaal één keer voor in closed_trades.

---

## 3.5 raw_events table

### Grain
1 row per canonical event envelope

### Doel
audit, replay, low-level debugging

### Hard rule
raw_events blijft append-only en onveranderd.

---

# 4. Validation rules

## 4.1 ID presence validation

Controleer:

- alle events hebben run_id
- alle events hebben session_id
- alle decision events hebben decision_cycle_id
- alle execution lifecycle events hebben trade_id
- alle order events hebben order_ref

---

## 4.2 Uniqueness validation

Controleer:

- decisions.decision_cycle_id is uniek
- closed_trades.trade_id is uniek

---

## 4.3 Referential validation

Controleer:

- elke guard_decision verwijst naar bestaande decision_cycle_id
- elke execution verwijst naar bestaande trade_id
- elke closed_trade verwijst naar bestaande trade lifecycle
- elke ENTER decision heeft trade_id mapping

---

## 4.4 Symbol consistency validation

Controleer:

- symbol-formaat consistent over producer / bridge / analytics
- geen broker alias leaks in canonical analytics tables

---

# 5. Hard rules

- Geen analyse zonder canonical identifiers
- Geen joins op timestamp-only logica
- Geen vrije interpretatie van lifecycle-koppelingen
- Geen broker-specifieke symbol aliases in analytics layer
- Geen derived datasets zonder gedefinieerde grain
- Geen ENTER zonder decision_cycle_id → trade_id linkage

---

# 6. Samenvatting

De Quant stack rust op drie dingen:

1. canonical identifiers
2. referential integrity
3. vaste dataset grains

Als deze drie goed zijn, wordt analytics betrouwbaar.  
Als deze drie zwak zijn, wordt elke metric verdacht.