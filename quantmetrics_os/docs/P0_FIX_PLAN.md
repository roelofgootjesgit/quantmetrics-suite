# P0 fix plan

## Doel

Dit document definieert het **P0 fixplan** voor de Quant stack op basis van de huidige QuantAnalytics-uitkomsten.

Doel:

Niet strategie tunen.  
Niet nieuwe metrics bouwen.  

Maar:

→ de **dataintegriteit, decision chain en trade lifecycle** repareren zodat analytics en strategy conclusions weer betrouwbaar worden.

---

## Sprint plan

Korte uitvoerindeling (volgorde is afhankelijk: B kan soms parallel met A starten zodra cycle-ID contract vastligt).

| Sprint | Scope | Hoofdrepo | Exit |
|--------|--------|-----------|------|
| **S1** | P0-A + P0-B: context op `signal_evaluated`; `decision_cycle_id` end-to-end op chain-events | QuantBuild | Acceptance uit P0-A en P0-B gehaald op test/backtest-run |
| **S2** | P0-C: funnel (detect/evaluate consistentie, Model A of expliciet B) | QuantBuild | Funnel-warnings weg, counts logisch |
| **S3** | P0-D: trade lifecycle (`trade_id`, fills, closes, open eindstaat) | QuantBridge (+ QuantBuild waar events ontstaan) | Lifecycle acceptance, gap verklaarbaar |
| **S4** | P0-E: validation rerun + analytics alleen rerun/checks | Hele stack + QuantAnalytics | Checklist onderaan volledig afgevinkt |

**Definition of Done (P0):** alle acceptance criteria in dit document, inclusief checklist, zijn waar op minimaal één volledige backtest of één volledige handelsdag met dezelfde analytics-pipeline.

---

# Kernconclusie

De huidige analytics-output toont dat de stack al echte signalen geeft over edge en blockers, maar dat interpretatie nog zwaar wordt verstoord door structurele upstream problemen.

De belangrijkste problemen zijn nu:

1. **context ontbreekt op producer-events**
2. **decision_cycle_id ontbreekt op een groot deel van chain-events**
3. **signal funnel is inconsistent**
4. **trade lifecycle is niet sluitend**
5. **guard-dominantie kan nog niet zuiver worden beoordeeld door ontbrekende context**

Daarom is dit document strikt een:

→ **repair plan voor producer + execution + logging correctness**

---

# Niet doen

Tijdens deze P0-fase doen we **niet**:

- geen strategy tuning
- geen guard-threshold tuning
- geen session-regel tuning
- geen exit-logica wijziging
- geen extra analytics features
- geen dashboardwerk

Alleen correctness.

---

# P0 Prioriteiten

## P0-A — Producer context correctness
## P0-B — Decision cycle integrity
## P0-C — Funnel correctness
## P0-D — Trade lifecycle correctness
## P0-E — Validation rerun

---

# P0-A — Producer context correctness

## Probleem

Analytics toont dat belangrijke contextvelden vrijwel ontbreken op `signal_evaluated`:

- `session` ~ nauwelijks aanwezig
- `setup_type` ~ nauwelijks aanwezig

Zonder deze velden zijn:

- expectancy per session
- expectancy per setup
- blocker analysis per session/setup
- guard diagnostics per context

niet betrouwbaar.

---

## Doel

Zorg dat **elke `signal_evaluated` row** minimaal deze context bevat:

- `session`
- `regime`
- `setup_type`
- `signal_type`
- `confidence`

Aanbevolen extra context:

- `side`
- `combo_count`
- `spread`
- `price_at_signal`

---

## Concrete fix checks

### QuantBuild — signal_evaluated emitter

Controleer:

- Wordt `payload_session` altijd gezet vóór emit?
- Wordt `payload_setup_type` altijd gezet vóór emit?
- Zit de data in runtime context, maar wordt ze niet doorgegeven?
- Is er fallback naar `<missing>` of `None`?
- Wordt session alleen op sommige codepaden gezet?
- Wordt setup_type alleen op detect gezet maar niet op evaluate?

---

## Vereiste fix

Voor elk codepad dat `signal_evaluated` emit:

- session verplicht invullen
- regime verplicht invullen
- setup_type verplicht invullen
- confidence verplicht invullen

Geen silent omissions.

---

## Acceptance criteria

P0-A is klaar als:

- `session` present_pct op `signal_evaluated` > 99%
- `setup_type` present_pct op `signal_evaluated` > 99%
- `regime` present_pct op `signal_evaluated` > 99%
- geen onverwachte `<missing>` meer in context completeness report

---

# P0-B — Decision cycle integrity

## Probleem

Analytics toont dat een groot deel van de chain-events geen `decision_cycle_id` heeft.

Gevolg:

- cycle funnel is onbetrouwbaar
- event correlation is beschadigd
- NO_ACTION analyse per cycle is verzwakt
- trade linkage degradeert

---

## Doel

Alle decision-chain events moeten consistent dezelfde `decision_cycle_id` dragen.

Verplicht op:

- `signal_detected`
- `signal_evaluated`
- `risk_guard_decision`
- `trade_action`

---

## Concrete fix checks

### QuantBuild — cycle ID generatie

Controleer:

- Waar wordt `decision_cycle_id` aangemaakt?
- Gebeurt dit vóór het eerste chain event?
- Wordt dezelfde ID doorgegeven aan alle vervolg-events?
- Wordt de ID alleen op sommige branches gezet?
- Gaat de ID verloren bij guard-evaluatie of action-emit?
- Is er per ongeluk een mix van:
  - event-local ID
  - trace ID
  - cycle ID
  - null / missing

---

## Vereiste fix

Eén evaluatiecyclus = exact één `decision_cycle_id`

Hard rule:

- de ID moet vroeg in de evaluatie worden aangemaakt
- de ID moet onderdeel zijn van het event context object
- alle emits binnen de cycle moeten deze context hergebruiken

Niet opnieuw genereren per event.

---

## Acceptance criteria

P0-B is klaar als:

- missing `decision_cycle_id` op chain rows = 0
- `decision_cycle_id` aanwezig op 100% van:
  - `signal_detected`
  - `signal_evaluated`
  - `risk_guard_decision`
  - `trade_action`
- cycle funnel aantallen zijn reproduceerbaar

---

# P0-C — Funnel correctness

## Probleem

Analytics toont een fysiek onmogelijke funnel:

- `signal_evaluated > signal_detected`

Dat betekent:

- detect events missen
- of evaluate events dubbel emitten
- of ordering / counting is inconsistent

---

## Doel

Herstel een logische decision funnel.

Gewenste minimale interpretatie:

- elke cycle heeft maximaal 1 terminal `trade_action`
- `signal_detected` en `signal_evaluated` moeten logisch gekoppeld zijn
- multi-eval per detect mag alleen als dit expliciet ontworpen en gelogd is

---

## Concrete fix checks

### QuantBuild — detect/evaluate flow

Controleer:

- Wordt `signal_detected` altijd geëmit als er later `signal_evaluated` komt?
- Kan een cycle meerdere `signal_evaluated` emits genereren?
- Wordt evaluate ook geëmit bij retry / same-bar / cooldown paths?
- Is `signal_detected` conditioneel, maar `signal_evaluated` onvoorwaardelijk?
- Zijn er codepaden waar detect wordt overgeslagen?
- Emit hetzelfde path per ongeluk meerdere evaluated rows?

---

## Vereiste fix

Kies expliciet één model:

### Model A — single-eval model (aanbevolen)
Per cycle:
- 1 detect
- 1 evaluate
- 0..n guards
- 1 trade_action

### Model B — multi-eval model
Alleen toegestaan als:
- er een expliciete `eval_stage` of `evaluation_pass` wordt gelogd
- analytics daarop aangepast wordt

Voor P0 is **Model A** aanbevolen.

---

## Acceptance criteria

P0-C is klaar als:

- `signal_detected >= signal_evaluated` op event-count basis, of zeer dicht bij elkaar met verklaarbare afwijking
- cycle funnel toont geen ordering anomaly
- warning `FUNNEL_EVAL_EXCEEDS_DETECT` verdwijnt
- warning `FUNNEL_ORDERING` verdwijnt

---

# P0-D — Trade lifecycle correctness

## Probleem

Analytics toont een enorme gap tussen:

- `order_filled`
- `trade_closed`

Dat betekent dat lifecycle reconstructie nu niet betrouwbaar is.

Mogelijke oorzaken:

- closes worden niet geëmit
- closes hebben geen correcte `trade_id`
- trades blijven open zonder expliciete open-status
- analyzer kan fills en closes niet goed joinen

---

## Doel

Maak de trade lifecycle sluitend en reconstrueerbaar.

Lifecycle:

`trade_action(ENTER)`  
→ `order_submitted`  
→ `order_filled`  
→ `trade_executed`  
→ `trade_closed`

Of expliciet:

→ trade blijft open aan einde run

---

## Concrete fix checks

### QuantBridge / execution layer

Controleer:

- Krijgt elke ENTER een `trade_id`?
- Draagt `order_submitted` dezelfde `trade_id`?
- Draagt `order_filled` dezelfde `trade_id`?
- Draagt `trade_executed` dezelfde `trade_id`?
- Draagt `trade_closed` dezelfde `trade_id`?
- Wordt `trade_closed` überhaupt altijd geëmit bij closure?
- Wordt close alleen lokaal bijgehouden maar niet gelogd?
- Gaat `trade_id` verloren tussen broker callback en event emitter?
- Zijn partial fills / netting / reverse closes goed gemodelleerd?
- Is er een verschil tussen broker position id en internal trade_id dat de join breekt?

---

## Vereiste fix

Er moeten maar twee legitieme toestanden zijn na fill:

### Toestand 1 — Gesloten trade
Dan moet bestaan:
- `trade_closed`
- met correcte `trade_id`
- en outcome metrics

### Toestand 2 — Open trade op einde run
Dan moet expliciet zichtbaar zijn:
- trade is nog open
- close ontbreekt niet per ongeluk

---

## Extra vereiste

Voeg indien nodig een expliciete open-position status artefact toe in analytics of execution snapshot, zodat:

- open trades
- closed trades
- missing closes

onderscheiden kunnen worden.

---

## Acceptance criteria

P0-D is klaar als:

- elke `order_filled` trade een consistente `trade_id` heeft
- `trade_closed` logging sluit aan op dezelfde `trade_id`
- `filled_minus_closed` is verklaarbaar
- lifecycle warning `LIFECYCLE_CLOSE_GAP` verdwijnt of wordt vervangen door expliciete open-position verklaring
- analytics kan correct rapporteren:
  - closed trades
  - open trades at end of run

---

# P0-E — Validation rerun

## Doel

Na fixes geen aannames maken.

De stack moet opnieuw draaien en opnieuw gevalideerd worden.

---

## Vereiste rerun

Draai minimaal:

- 1 volledige backtest run
of
- 1 volledige handelsdag

Gebruik exact dezelfde analytics pipeline.

---

## Verplichte checks na rerun

### Data quality
- missing `decision_cycle_id` = 0
- session completeness > 99%
- setup_type completeness > 99%

### Funnel
- geen `FUNNEL_EVAL_EXCEEDS_DETECT`
- geen `FUNNEL_ORDERING`

### Lifecycle
- fills en closes logisch verklaarbaar
- geen onverklaarde lifecycle gap

### Summary layer
- HIGH warnings voor context / cycle / funnel verdwijnen
- key findings verschuiven van data integrity → echte strategy insights

---

# Verwachte verschuiving na geslaagde P0

## Nu
De headline is ongeveer:

- data/context integrity issues dominate interpretation

## Na P0
De headline moet verschuiven naar iets als:

- regime selectivity and guard configuration dominate performance
- expansion edge visible; compression neutral; risk policy suppresses throughput

Met andere woorden:

→ pas na P0 mag de analyzer een echte strategy machine worden

---

# Code-aanpak per repo

## QuantBuild — fixen

Focus:

- `signal_detected`
- `signal_evaluated`
- `risk_guard_decision`
- `trade_action`

Te fixen:

- context propagation
- decision_cycle_id propagation
- detect/evaluate consistency
- terminal chain completeness

---

## QuantBridge — fixen

Focus:

- `order_submitted`
- `order_filled`
- `trade_executed`
- `trade_closed`

Te fixen:

- `trade_id` propagation
- lifecycle completeness
- close-event emission
- mapping internal trade ↔ broker position

---

## QuantLog — controleren, niet verbouwen

Focus:

- schema validation
- envelope integrity
- required fields aanwezig
- event storage correct

QuantLog is waarschijnlijk niet het probleem, tenzij:
- required fields niet worden afgedwongen
- events zonder critical IDs toch door schema glippen

---

## QuantAnalytics — alleen opnieuw draaien

Focus:

- rerun
- warnings check
- key findings check
- geen nieuwe features

---

# Acceptance checklist

## P0 is pas klaar als al deze punten waar zijn

### Producer
- [ ] `session` aanwezig op >99% van `signal_evaluated`
- [ ] `setup_type` aanwezig op >99% van `signal_evaluated`
- [ ] `regime` aanwezig op >99% van `signal_evaluated`
- [ ] `decision_cycle_id` aanwezig op 100% van chain-events

### Funnel
- [ ] `signal_detected` en `signal_evaluated` logisch consistent
- [ ] geen funnel ordering anomaly meer
- [ ] elke cycle eindigt in exact één terminal `trade_action`

### Lifecycle
- [ ] elke fill heeft consistente `trade_id`
- [ ] closes zijn correct gelogd of expliciet nog open
- [ ] lifecycle gap is verklaard of verdwenen

### Analytics
- [ ] HIGH warnings voor context / cycle / funnel zijn verdwenen
- [ ] key findings worden gedomineerd door echte strategy insights, niet door databreuken

---

# Samenvatting

Dit P0 fixplan draait om één principe:

**eerst de machine repareren, dan pas de edge optimaliseren**

De analyzer heeft zijn werk gedaan.

Hij zegt nu helder:

- edge bestaat
- exits zijn niet het hoofdprobleem
- risk en regime doen ertoe
- maar data-integriteit breekt nog de interpretatie

Daarom is de juiste volgorde nu:

1. fix producer context
2. fix decision cycle IDs
3. fix funnel correctness
4. fix trade lifecycle
5. rerun analytics
6. pas daarna strategy tuning
