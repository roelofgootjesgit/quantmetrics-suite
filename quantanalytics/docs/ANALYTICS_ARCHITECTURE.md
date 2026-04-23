Goed. Dan maken we nu geen code, geen stappenplan — maar een **technisch handboek**.
Dit wordt jouw **referentie-architectuur** voor de analytics module.

---

# QUANTMETRICS ANALYTICS — HANDBOEK

---

## 1. Probleem definitie

De QuantMetrics stack genereert data via:

* QuantBuild → beslissingen
* QuantBridge → execution
* QuantLog → opslag (JSONL, event-based, append-only)

De huidige situatie:

* Data wordt correct gelogd
* Events zijn rijk en reproduceerbaar
* Maar:

  * er is **geen gestructureerde analyselaag**
  * er is **geen causale interpretatie**
  * er is **geen feedback richting strategie**

De ontbrekende component:

> Een **deterministische analytics pipeline** die events omzet naar inzicht en systeemverbetering.

---

## 2. Fundamentele principes

Deze module moet voldoen aan:

### 2.1 Source of truth

* QuantLog is leidend
* Analytics mag:

  * alleen lezen
  * nooit muteren

### 2.2 Reproduceerbaarheid

Elke analyse moet:

* opnieuw te draaien zijn
* deterministisch zijn
* afhangen van:

  * input events
  * versie van analysecode

### 2.3 Scheiding van verantwoordelijkheden

| Layer     | Verantwoordelijkheid |
| --------- | -------------------- |
| QuantLog  | opslag van events    |
| Analytics | interpretatie        |
| Strategy  | beslissingen         |

### 2.4 Geen business logic upstream

* Geen analyse in QuantBuild
* Geen metrics in QuantBridge
* Alles downstream

---

## 3. Data model — denken in events

De volledige analyse begint bij:

> **Event = atomair feit**

Een event bevat:

* wat gebeurde er
* wanneer
* in welke context
* met welke correlaties

Belangrijke velden:

```text
timestamp_utc
event_type
run_id
session_id
trace_id
source_seq
payload
```

---

## 4. Event → Analyse transformatie

Dit is de kern van het systeem.

### 4.1 Probleem

Events zijn:

* lineair
* atomair
* technisch

Maar analyse vereist:

* context
* aggregatie
* betekenis

---

### 4.2 Oplossing: 3 transformatielagen

#### LAYER 1 — Bronze (Raw → Structured)

Doel:

* JSON → kolommen
* events blijven 1-op-1 behouden

Eigenschappen:

* geen interpretatie
* alleen normalisatie

---

#### LAYER 2 — Silver (Context → Entities)

Doel:

* events groeperen tot betekenisvolle eenheden

Nieuwe entiteiten:

* signal cycle
* trade lifecycle
* position lifecycle

Dit is waar **log → verhaal** wordt.

---

#### LAYER 3 — Gold (Metrics → Inzicht)

Doel:

* meetbare outputs

Voorbeelden:

* expectancy
* hitrate
* drawdown
* no-trade reasons
* regime performance

---

## 5. Kern entiteiten

### 5.1 Signal Cycle

Definitie:

> Eén volledige besliscyclus van de strategie op één moment

Bestaat uit:

```text
signal_detected
→ signal_evaluated
→ risk_guard_decision
→ trade_action
```

Belang:

* verklaart waarom trades wel/niet gebeuren

---

### 5.2 Trade Lifecycle

Definitie:

> Alles wat gebeurt vanaf order tot exit

Bestaat uit:

```text
order_submitted
→ order_filled
→ position_open
→ position_update
→ position_closed
```

Belang:

* performance analyse
* execution kwaliteit

---

### 5.3 Position Lifecycle

Definitie:

> De levensduur van een positie

Belang:

* MAE / MFE
* exit kwaliteit
* risk behaviour

---

## 6. Analyse dimensies

De kracht zit in **combinaties**.

Elke analyse moet kunnen splitsen op:

### 6.1 Strategie dimensie

* strategy
* setup type
* module combinations

### 6.2 Markt dimensie

* symbol
* regime (trend / compression / expansion)
* volatility context

### 6.3 Tijd dimensie

* session (Asia / London / NY)
* tijd van dag
* dag / week

### 6.4 Systeem dimensie

* filters
* cooldowns
* risk guards
* execution state

---

## 7. Analyse types

### 7.1 Funnel analyse

Vraag:

> Waar valt de pipeline uit?

Voorbeeld:

```text
1000 signal_detected
→ 300 signal_evaluated
→ 120 risk_allowed
→ 20 trades
```

→ Bottleneck zichtbaar

---

### 7.2 No-trade analyse

Vraag:

> Waarom worden er geen trades genomen?

Output:

```text
cooldown_active: 60%
regime_blocked: 20%
no_setup: 10%
risk_blocked: 10%
```

---

### 7.3 Performance analyse

Per trade:

* pnl
* pnl_r
* MAE / MFE
* duration

Aggregaties:

* expectancy
* hitrate
* profit factor

---

### 7.4 Context analyse

Voorbeeld:

```text
Regime: Expansion → +0.4R expectancy
Regime: Compression → -0.1R expectancy
```

→ directe strategie feedback

---

### 7.5 Filter impact analyse

Vraag:

> Welke filters killen edge?

Methode:

* vergelijk:

  * raw signals
  * filtered signals
  * executed trades

---

### 7.6 Behaviour analyse

Vraag:

> Hoe gedraagt het systeem zich?

Voorbeelden:

* cooldown gedrag
* session gating
* risk throttling
* latency tussen events

---

## 8. Storage strategie

### 8.1 Waarom niet alleen JSONL

JSONL is:

* goed voor logging
* slecht voor analyse

Problemen:

* traag
* geen kolommen
* moeilijk joinen

---

### 8.2 Waarom Parquet

Parquet is:

* columnar
* snel
* goed voor aggregaties

---

### 8.3 Storage lagen

```text
analytics_data/

bronze/
  events/

silver/
  signal_cycles/
  trade_lifecycles/

gold/
  metrics/

reports/
```

---

### 8.4 Partitioning

Altijd partitioneren op:

```text
date
run_id
```

Optioneel:

```text
strategy
symbol
```

---

## 9. Output types

### 9.1 Diagnostic report (mens)

Voorbeeld:

```text
Run: 2026-04-19

Trades: 0

Top reasons:
- cooldown_active: 64%
- compression_regime: 22%

Insight:
System is over-filtered during NY session.
```

---

### 9.2 Feedback artifact (systeem)

JSON:

```json
{
  "issue": "low_trade_frequency",
  "root_causes": [
    "cooldown_active",
    "compression_regime"
  ],
  "suggestions": [
    "reduce cooldown duration",
    "disable compression trades"
  ]
}
```

---

### 9.3 CLI — `research` rapport (MVP)

De CLI (`python -m quantmetrics_analytics.cli.run_analysis`) ondersteunt **`--reports research`**: een tekstrapport met datakwaliteit, decision-cycle funnel, lifecycle open/gesloten, context-completeness op `signal_evaluated`, guard-diagnostiek, expectancy-slices en exit-efficiency. Zelfde blokken zitten in **`build_run_summary`** / **`--run-summary-json`** en de Markdown-spiegel **`--run-summary-md`**.

Implementatie: package-module **`quantmetrics_analytics.analysis.extended_diagnostics`**. Specificatie-context: **`quantmetrics_os`** `docs/ANALYTICS_OUTPUT_GAPS.md`.

---

## 10. Closed feedback loop

Dit is waar alles samenkomt.

```text
Analyse → inzicht → aanpassing → nieuwe run → nieuwe data
```

Voorbeelden:

* strategy parameters aanpassen
* filters tweaken
* risk aanpassen
* sessions aanpassen

---

## 11. Wat dit systeem uiteindelijk moet kunnen

### 11.1 Verklaren

* Waarom trades niet gebeuren
* Waarom trades verliezen

### 11.2 Meten

* Edge (expectancy)
* Stability
* Drawdown

### 11.3 Detecteren

* bottlenecks
* overfitting gedrag
* regime afhankelijkheid

### 11.4 Adviseren

* parameter changes
* filter changes
* strategy improvements

---

## 12. Wat dit NIET is

Belangrijk:

Dit systeem is **niet**:

* een dashboard tool
* een grafiek tool
* een BI tool

Het is:

> een **research engine voor trading systems**

---

## 13. Samenvatting (essentie)

Je bouwt dit:

```text
QuantLog (events)
    ↓
Analytics Engine
    ↓
Structured datasets
    ↓
Insights
    ↓
Feedback
    ↓
QuantBuild verbetering
```

---

## 14. Volgende stap

Niet bouwen.

👉 Dit handboek staat hier:

```text
docs/ANALYTICS_ARCHITECTURE.md
```

---

Daarna gaan we:

→ dit vertalen naar **MVP pipeline (code)**

→ daarna naar **eerste echte analyse op jouw live data**

En daar gaat het interessant worden:

want dan ga je voor het eerst zien waar je systeem echt stukloopt.
