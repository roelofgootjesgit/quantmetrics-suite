# QUANTMETRICS ANALYTICS — SPRINT PLAN

Vertical slices op QuantLog-data: elke sprint levert werkende CLI-output op echte data.

---

## 1. Probleem vertaling

Wat doen we hier?

We breken de analytics module op in vertical slices die:

* direct draaien op jouw QuantLog data
* direct inzicht geven
* stap voor stap uitbreiden naar volledige pipeline

**Belangrijk:** elke sprint moet eindigen met een werkende CLI-output op echte data.

---

## 2. Architectuur strategie (voor sprints)

We bouwen een bottom-up pipeline:

`Ingestion → Normalize → Bronze → Silver → Analysis → Reports`

Maar we shippen **per sprint een slice**, niet per layer.

---

## 3. Sprint overzicht

Vijf sprints (tempo + Cursor workflow):

### Sprint 1 — RAW → STRUCTURED (FOUNDATION)

**Doel:** Van JSONL → DataFrame → eerste inzicht.

**Scope:**

* ingestion (load JSONL)
* normalize (flatten events)
* basic CLI

**Output:** `python -m quantmetrics_analytics.cli.run_analysis` (of pad naar `cli/run_analysis.py`)

**Resultaat (voorbeeld):**

```text
Total events: 12,345
Event types:
- signal_detected: 3,200
- trade_action: 8,100
...
```

**Waarom dit belangrijk is:**

* checkt of je data klopt
* checkt of je pipeline werkt
* geen analyse, alleen zichtbaarheid

---

### Sprint 2 — NO TRADE INTELLIGENCE (snelle win)

**Doel:** Antwoord op het huidige probleem: *waarom geen trades?*

**Scope:**

* filter `trade_action`
* analyse `decision == NO_ACTION`
* reason breakdown

**Output — NO TRADE ANALYSIS:**

```text
cooldown_active: 62%
compression_regime: 21%
no_setup: 10%
risk_blocked: 7%
```

**Impact:** dit raakt direct het live probleem (geen trades, veel NO_ACTION).

---

### Sprint 3 — SIGNAL FUNNEL (pipeline debug)

**Doel:** Begrijpen waar de pipeline stopt.

**Scope:**

* `signal_detected`
* `signal_evaluated`
* `risk_guard_decision`
* `trade_action`

**Output — SIGNAL FUNNEL:**

```text
Detected: 1000
Evaluated: 320
Risk Passed: 140
Trades: 18
```

**Extra:** drop-off percentages; optioneel per regime / session.

---

### Sprint 4 — TRADE LIFECYCLE + PERFORMANCE

**Doel:** Edge meten.

**Scope:**

* order → position → close
* pnl, pnl_r
* MAE / MFE

**Output — PERFORMANCE:**

```text
Trades: 42
Winrate: 48%
Expectancy: +0.22R
Avg MAE: -0.35R
Avg MFE: +0.78R
```

---

### Sprint 5 — CONTEXT INTELLIGENCE (real edge)

**Doel:** Waar zit de edge echt?

**Scope:** performance per regime, session, strategy.

**Output — REGIME PERFORMANCE:**

```text
Expansion: +0.41R
Trend: +0.12R
Compression: -0.09R
```

---

## 4. Data flow per sprint

Elke sprint bouwt voort op de vorige:

| Sprint | Levert |
| ------ | ------ |
| 1 | events DataFrame |
| 2 | gefilterde decisions |
| 3 | gegroepeerde signal cycles |
| 4 | trade lifecycles |
| 5 | geaggregeerde insights |

---

## 5. Concrete Cursor workflow

Per sprint:

1. **Module:** werk onder package `quantmetrics_analytics/` (`ingestion/`, `processing/`, `analysis/`, `cli/`).
2. **Code:** voeg typisch één analysebestand toe, bv. `analysis/no_trade_analysis.py`.
3. **CLI:** breid `cli/run_analysis.py` uit — elke sprint één analyse, print output naar stdout.

---

## 6. Belangrijke regel (kritisch)

**Niet doen:**

* meteen dashboards bouwen
* alles tegelijk willen
* perfecte datamodellen eerst afmaken

**Wel doen:**

* per sprint één vraag beantwoorden
* direct op echte logs draaien
* fouten zichtbaar maken

---

## 7. Prioriteit

Als het systeem live draait, weinig trades, veel NO_ACTION:

**Sprintvolgorde is niet optioneel:** Sprint 1 → **Sprint 2 (kritisch)** → Sprint 3 → daarna performance (Sprint 4–5).

---

## 8. Scaffold (startpunt)

Package-layout (repository-root):

```text
quantmetrics_analytics/
  ingestion/
  processing/
  analysis/
  cli/
    run_analysis.py
```

Minimuminhoud van `cli/run_analysis.py` tot Sprint 1 uitbreiding:

```python
print("QuantMetrics Analytics MVP")
```

(Zie repository: deze structuur kan al aanwezig zijn als lege MVP.)
