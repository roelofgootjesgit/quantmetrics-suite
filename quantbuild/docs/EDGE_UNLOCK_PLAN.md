# QuantBuild — Edge Unlock Plan

## Van 0 live trades naar meetbare expectancy

---

# Doel

Het doel is niet om meteen production-ready te zijn.

Het doel is om in drie fasen van:

* te weinig trades
* te veel filters
* geen live waarheid

naar:

* voldoende throughput
* meetbare expectancy
* data-gedreven filters

te gaan.

---

# Kernprincipe

```text
Fase 1: Throughput verhogen
Fase 2: Winrate / expectancy analyseren
Fase 3: Filters opnieuw bouwen op basis van data
```

Niet op gevoel.

Niet op aannames.

Niet op "mooie setups".

---

# Fase 1 — Throughput verhogen

## Doel

De signal engine moet eindelijk genoeg trades produceren om de waarheid te laten zien.

## Target

Binnen 5–10 handelsdagen wil je:

* minimaal 50–100 trades
* liever 100+
* voldoende spreiding over sessies/regimes

## Waarom

Zonder trade volume weet je niets over:

* winrate
* expectancy
* drawdown-profiel
* welke filters echt waarde toevoegen

---

## 1.1 Mode

Gebruik alleen:

```yaml
system_mode: EDGE_DISCOVERY
```

---

## 1.2 Guards die UIT moeten

Voor deze fase zet je non-essentiële suppressie uit:

* regime filter = uit
* session filter = uit
* cooldown = uit of minimaal
* position limit = ruim
* news veto = uit voor discovery-test
* max trades per session = ruim of uit

---

## 1.3 Guards die AAN blijven

Je wilt geen totale chaos. Dus alleen catastrophische guards blijven aan:

* daily loss cap
* hard equity kill switch
* spread safety
* broker sanity / order safety

---

## 1.4 Strategy versoepeling

Doel: meer geldige entries doorlaten.

Tijdelijk versoepelen:

* `combo_min_modules`
* trigger strictness
* displacement strictness
* eventueel regime sensitivity

Belangrijk:

je doet dit **tijdelijk voor discovery**, niet als eindconfig.

---

## 1.5 Logging die nu verplicht is

Per trade / signal minimaal loggen:

* system_mode
* signal_detected
* trade_action
* reason
* session
* regime
* direction
* combo_active_modules_count
* trend_pillar_ok
* liquidity_pillar_ok
* trigger_ok
* structure_ok
* entry_signal

Extra verplicht:

* blocked_by guard
* bypassed_by_mode
* risk_guard_decision

---

## 1.6 Output die je elke dag nodig hebt

Per dag wil je direct zien:

* total signals
* total entries
* signal → entry ratio
* top blockers
* session mix
* regime mix
* trade count

---

## 1.7 Acceptance voor Fase 1

Fase 1 is geslaagd als:

1. live/demo eindelijk echte `ENTER` events laat zien
2. trade count niet meer structureel 0 is
3. blockers verschuiven van suppressie naar echte strategy-uitkomsten
4. je minimaal tientallen trades kunt verzamelen

---

# Fase 2 — Winrate en expectancy analyseren

## Doel

Niet meer vragen:

* "pakt hij trades?"

Maar:

* **"hebben die trades edge?"**

---

## 2.1 Vereiste sample

Ga niet analyseren op 3 trades.

Minimum:

* 50 trades voor eerste ruwe indruk
* 100 trades voor bruikbare eerste analyse
* 200 trades voor serieuzer beeld

---

## 2.2 Metrics die je moet meten

Per run / periode:

* trade count
* winrate
* average R
* expectancy
* profit factor
* max drawdown
* MAE
* MFE
* hold time
* session performance
* regime performance
* long vs short performance

---

## 2.3 Breakdown die je verplicht moet doen

Niet alleen totaalresultaat.

Je moet splitsen op:

### Sessies

* Asia
* London
* New York

### Regimes

* trend
* expansion
* compression

### Richting

* long
* short

### Moduleprofiel

* combo count
* trigger true/false
* trend pillar true/false
* liquidity pillar true/false

---

## 2.4 Belangrijkste vragen in Fase 2

1. Heeft raw signal flow positieve expectancy?
2. Welke sessies zijn winstgevend?
3. Welke regimes zijn winstgevend?
4. Zijn longs of shorts beter?
5. Welke blockers blijken achteraf terecht?
6. Welke filters hebben waarschijnlijk edge vernietigd?

---

## 2.5 Mogelijke uitkomsten

### Uitkomst A — Raw expectancy positief

Goed nieuws.

Dan weet je:

* de signal engine leeft
* filters mogen terugkomen, maar alleen slim

### Uitkomst B — Raw expectancy neutraal / licht negatief

Dan kan filtering nog steeds waarde toevoegen.

### Uitkomst C — Raw expectancy zwaar negatief

Dan zit de zwakte in signal quality, niet alleen suppressie.

---

## 2.6 Acceptance voor Fase 2

Fase 2 is geslaagd als je objectief kunt zeggen:

* of de raw engine edge heeft
* in welke context edge zit
* waar de zwakke clusters zitten
* welke filters kandidaten zijn om terug te bouwen

---

# Fase 3 — Filters opnieuw bouwen op basis van DATA

## Doel

Nu pas ga je filters terugbrengen.

Niet als religie.

Niet als aannames.

Maar als empirische selectie.

---

## 3.1 Volgorde van herintroductie

Filters één voor één terugzetten.

Niet tegelijk.

### Aanbevolen volgorde

1. session filter
2. regime filter
3. cooldown logic
4. position limits
5. news veto
6. extra risk strictness

---

## 3.2 Regel voor elke filter

Een filter mag alleen terugkomen als hij aantoonbaar:

* expectancy verhoogt
* of drawdown materieel verlaagt
* zonder throughput kapot te maken

---

## 3.3 Wat je per filter test

Voor elke filter vergelijk je:

* trade count
* expectancy
* PF
* DD
* enter rate

Voorbeeld:

| Variant          | Trades | Expectancy |   PF | DD |
| ---------------- | -----: | ---------: | ---: | -: |
| Raw discovery    |    120 |      0.08R | 1.18 | 9% |
| + session filter |     78 |      0.14R | 1.32 | 7% |
| + regime filter  |     41 |      0.12R | 1.29 | 6% |

Dan zie je pas of een filter echt helpt.

---

## 3.4 Filters die vaak slecht zijn

Waarschuwing:

deze filters zijn vaak te agressief als ze hard binary worden gemaakt:

* regime block
* session hard block
* cooldown na alles
* teveel max trades caps

Vaak is beter:

* risk schalen
* priority verlagen
* confidence score aanpassen

In plaats van:

```text
BLOCK
```

---

## 3.5 Slimme eindvorm

Je wilt uiteindelijk van hard filters naar:

```text
signal score + risk scaling + selective veto
```

Dus bijvoorbeeld:

* trend regime: 1.0R
* expansion: 0.75R
* compression: 0.25R

In plaats van:

* compression = nooit traden

---

## 3.6 Acceptance voor Fase 3

Fase 3 is geslaagd als:

1. filters aantoonbaar waarde toevoegen
2. throughput niet instort
3. production mode beter is dan raw discovery
4. je uiteindelijk een slimmere, data-gedreven production stack hebt

---

# Praktische sprintindeling

## Sprint 1 — Unlock

* EDGE_DISCOVERY live/demo draaien
* suppressie uit
* logging controleren
* eerste 20–50 trades verzamelen

## Sprint 2 — Sample bouwen

* 50–100+ trades verzamelen
* daily review
* trade outcome metrics opslaan

## Sprint 3 — Analyse

* expectancy / PF / DD per cluster
* session / regime / direction splits

## Sprint 4 — Filter return

* 1 filter tegelijk terug
* vergelijken met baseline
* alleen behouden bij aantoonbare winst

---

# Beslisboom

## Als je in Fase 1 nog steeds bijna geen trades krijgt

Dan zit het probleem nog in:

* live/backtest mismatch
* strategy logic
* data alignment

## Als je in Fase 1 veel trades krijgt maar Fase 2 is negatief

Dan is de raw engine zwakker dan gedacht.

## Als je in Fase 2 positief bent

Dan mag je Fase 3 in en filters opnieuw testen.

---

# Dagelijkse operator routine

Elke dag vastleggen:

* mode
* trades
* enter rate
* blockers
* top sessions
* top regimes
* PnL / R
* opvallende anomalies

---

# Harde regels

1. Geen filter terugzetten zonder data
2. Geen conclusies trekken op mini-sample
3. Geen production claims doen in discovery-fase
4. Eerst waarheid, dan optimalisatie

---

# Definitie van succes

Succes is niet:

* weinig trades
* mooie charts
* perfecte setups

Succes is:

```text
genoeg trades + meetbare expectancy + filters die op bewijs terugkomen
```

---

# Mentor conclusie

Je hebt nu de juiste richting gekozen.

Dit is hoe een echte desk werkt:

1. throughput creëren
2. edge meten
3. filters alleen behouden als ze aantoonbaar waarde toevoegen

Alles daarbuiten is ruis.
