# QuantLog Uitleg

## Wat is QuantLog?

QuantLog is de observability- en waarheidlaag van de Quant stack.

In simpele termen:

- `QuantBuild` beslist (signal/risk/action)
- `QuantBridge` voert uit (orders/broker/account state)
- `QuantLog` legt alles vast, valideert het, en maakt replay mogelijk

QuantLog is dus geen gewone logger, maar een **System of Record** voor tradingbeslissingen.

---

## Waarom QuantLog belangrijk is

Zonder QuantLog zie je alleen uitkomsten (PnL, win/loss), maar niet de oorzaken.

Met QuantLog kun je aantonen:

- waarom een trade genomen is
- waarom een trade geblokkeerd is
- of execution of strategy het probleem was
- of guardrails en governance echt gewerkt hebben

Dit maakt de stap van "bot" naar "professionele trading infrastructuur".

---

## Kernprincipes

1. **Canoniek event schema**  
   Alle systemen loggen in dezelfde event-structuur.

2. **Append-only opslag**  
   Events worden toegevoegd, niet herschreven.

3. **Deterministische replay**  
   Volgorde wordt robuust bepaald via:
   - `timestamp_utc`
   - `source_seq`
   - `ingested_at_utc`

4. **Contract-validatie**  
   Eventkwaliteit wordt afgedwongen met validator, niet met aannames.

5. **Fail-open trading, fail-closed audit**  
   Trading mag doorlopen bij loggingproblemen, maar audit-gaps moeten zichtbaar zijn.

---

## Wat QuantLog concreet biedt

## 1) Validate

Met `validate-events` check je of events schema-compliant zijn:

- verplichte velden aanwezig
- enums correct
- payloads correct
- correlatievelden correct

## 2) Replay

Met `replay-trace` reconstrueer je een volledige beslisketen:

`signal -> guard -> action -> order -> fill/reject`

## 3) Summary

Met `summarize-day` krijg je operationele dagcijfers:

- events total
- trades attempted/filled
- blocks
- rejects
- slippage stats

## 4) Ingest health

Met `check-ingest-health` detecteer je ingest gaps en kun je `audit_gap_detected` events emitten.

## 5) Run quality score

Met `score-run` krijg je een kwaliteitsscore (0-100) voor een run/dataset, inclusief penalties voor:

- errors/warnings
- duplicates
- out-of-order events
- missing trace IDs
- audit gaps

---

## Eventmodel in het kort

Elk event bevat minimaal:

- `event_id`
- `event_type`
- `event_version`
- `timestamp_utc`
- `ingested_at_utc`
- `source_system`
- `source_component`
- `environment`
- `run_id`
- `session_id`
- `source_seq`
- `trace_id`
- `severity`
- `payload`

Belangrijk: deze velden maken cross-system correlatie en betrouwbare replay mogelijk.

---

## Correlation model (causaliteit)

QuantLog gebruikt meerdere IDs die samen een causality graph vormen:

- `trace_id`: beslissing lifecycle
- `order_ref`: order lifecycle
- `position_id`: positie lifecycle
- `run_id`: bot-run context
- `session_id`: process/boot context

Deze combinatie maakt het mogelijk om niet alleen events te zien, maar oorzakelijke ketens te reconstrueren.

---

## Decision semantiek

Om overlap te voorkomen:

- `risk_guard_decision.decision` gebruikt: `ALLOW|BLOCK|REDUCE|DELAY`
- `trade_action.decision` gebruikt: `ENTER|EXIT|REVERSE|NO_ACTION`

Hiermee blijven guard-beslissingen en trade-intenties logisch gescheiden.

---

## Positie in de totale stack

```text
Market Data / News
        |
    QuantBuild
 (signal -> risk -> action)
        |
   QuantBridge
 (orders -> broker -> fills)
        |
      Broker

Alle events
        |
     QuantLog
        |
Replay / Metrics / Run Quality / Audit
```

Belangrijk onderscheid:

- QuantBuild beslist
- QuantBridge voert uit
- QuantLog verklaart wat er gebeurde

---

## Typische workflow

1. Draai strategie/execution.
2. Valideer events (`validate-events`).
3. Replay kritieke traces (`replay-trace`).
4. Check dagmetrics (`summarize-day`).
5. Check ingest health (`check-ingest-health`).
6. Score de run (`score-run`).
7. Gebruik alleen kwalitatief goede runs voor evaluatie.

---

## Stabiliteitsregels (architectuur)

1. Schema zoveel mogelijk backward compatible houden.  
2. Oude events moeten replaybaar blijven over versies heen.  
3. QuantLog houdt geen business logic voor strategy/risk beslissingen.  
4. Run quality gating is verplicht voor datasets die gebruikt worden in evaluatie.  
5. QuantLog blijft event spine + replay + quality layer, geen BI monoliet.

---

## Wat QuantLog bewust niet is

QuantLog v1 is **niet**:

- een full BI platform
- een dashboard suite
- een ML feature warehouse

QuantLog v1 is bewust klein gehouden als stabiele event spine:

> immutable events + replay + quality gating

---

## Event versioning beleid

- Gebruik `event_version` op elk event.
- Nieuwe velden toevoegen heeft voorkeur boven hernoemen/verwijderen.
- Bij breaking wijzigingen: nieuwe versie introduceren en replay compatibiliteit borgen.
- Validator en fixtures moeten beide versies kunnen controleren tijdens migraties.

---

## Samenvatting

QuantLog zorgt ervoor dat je tradingstack niet alleen trades maakt, maar ook uitlegbaar, controleerbaar en reproduceerbaar is.

Dat is de basis voor professionele opschaling:

- betere incidentanalyse
- betrouwbaardere strategie-evaluatie
- veiligere paper -> live migratie
- sneller en data-gedreven verbeteren

Kerncyclus:

`Trade -> Log -> Replay -> Analyse -> Verbetering -> Trade`

