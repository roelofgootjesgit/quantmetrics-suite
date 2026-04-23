# QuantLog Ops Console — Sprint C Handbook

## Operator Intelligence Layer (Lightweight)

---

# 1. Doel van Sprint C

Sprint C voegt **intelligentie** toe bovenop je bestaande operator console.

Niet met AI.
Niet met complexiteit.

Maar met:

> **gerichte inzichten die direct helpen bij strategie-evaluatie**

---

## Kernvraag van Sprint C

> “Wat moet ik NU aanpassen aan mijn strategie op basis van wat ik zie?”

Sprint A → betrouwbaar
Sprint B → bruikbaar
Sprint C → **inzichtgevend**

---

# 2. Scope van Sprint C

## In scope

* Run comparison (A vs B)
* Rule-based anomaly hints
* Daily summary (auto gegenereerd)
* Simple insight layer boven bestaande data

## Niet in scope

* AI / LLM integratie
* Machine learning
* Predictive analytics
* PnL-analyse
* Complexe statistiek
* Database

---

# 3. Design principes

## 3.1 Simple rules > slimme modellen

Alle inzichten moeten:

* transparant zijn
* reproduceerbaar
* debugbaar

---

## 3.2 Operator-first insights

Niet:

> “hier zijn data”

Maar:

> “dit is wat je moet weten”

---

## 3.3 Geen black box

Elke insight moet uitlegbaar zijn:

* welke data?
* welke regel?
* waarom deze conclusie?

---

## 3.4 Realtime bruikbaar

Insights moeten direct helpen bij:

* debuggen
* strategie aanpassen
* edge detectie

---

# 4. Sprint C Features

---

# 4.1 Daily Summary (AUTO INSIGHT)

## Doel

Bij openen van een dag direct een **samenvatting van gedrag van de bot**

---

## Locatie

Bovenaan:

* Daily Control
* Decision Breakdown

---

## Output voorbeeld

```id="p0l2v3"
Today summary:

- No trades executed
- 312 signals evaluated
- Dominant blocker: cooldown_active (63%)
- Regime: compression dominated (71%)
- System active until 14:59 UTC
```

---

## Data input

Gebruik bestaande:

* summarizer
* health metrics
* no_trade_explainer
* scan_day_jsonl_stats

---

## Implementatie

Nieuw bestand:

```text
quantlog_ops/services/daily_summary.py
```

### Functie

```python id="j2k4m9"
def build_daily_summary(summary, health_metrics, explainer_lines):
    ...
```

---

## Regels

* Als entries == 0 → “No trades executed”
* Als entries > 0 → “X trades executed”
* Toon dominante blocker (>40%)
* Toon dominante regime (>50%)
* Toon laatste activiteit

---

# 4.2 Run Comparison (CORE FEATURE)

## Doel

Vergelijk 2 runs om strategiegedrag te analyseren

---

## Nieuwe pagina

```text
pages/5_Run_Comparison.py
```

---

## UI

### Selectie

* Day
* Run A (dropdown)
* Run B (dropdown)

---

## Output

### Tabel

| Metric    | Run A | Run B |
| --------- | ----- | ----- |
| Events    | 1200  | 980   |
| Signals   | 300   | 280   |
| Entries   | 5     | 0     |
| No Action | 295   | 280   |
| Errors    | 1     | 0     |

---

### Ratio’s

```id="u8m4k1"
signal → entry
signal → trade_action
```

---

### Blocker comparison

```id="y7n2z5"
cooldown_active:
  Run A: 40%
  Run B: 70%

compression:
  Run A: 50%
  Run B: 80%
```

---

### Regime comparison

* pie chart of bar chart
* per run naast elkaar

---

## Implementatie

Gebruik bestaande:

* summarizer
* health
* quick filters

---

## Service

```text
quantlog_ops/services/run_compare.py
```

### Functie

```python id="q3d6v2"
def compare_runs(run_a_rows, run_b_rows):
    ...
```

---

## Belangrijk

Geen fancy diff engine.

Alleen:

* counts
* ratios
* top redenen

---

# 4.3 Anomaly Hints (RULE ENGINE)

## Doel

Automatisch opvallende situaties detecteren

---

## Nieuwe module

```text
quantlog_ops/services/anomaly_hints.py
```

---

## Output

```python id="n5k8x1"
[
  "No trades despite 300+ signals",
  "95% of signals blocked by cooldown",
  "Compression regime dominates (>80%)",
  "No signals during NY session",
]
```

---

## Regels (MVP)

### 1. No trades but signals

```id="m1s2t3"
if entries == 0 and signals > 50:
```

---

### 2. Extreme blocker

```id="k2l3m4"
if top_reason_pct > 80:
```

---

### 3. Regime dominance

```id="p9q8r7"
if top_regime_pct > 80:
```

---

### 4. Low activity

```id="h1j2k3"
if total_events < threshold:
```

---

### 5. Missing signals

```id="d4f5g6"
if signals == 0:
```

---

## Integratie

Toon bovenaan:

* Daily Control
* Decision Breakdown

---

# 4.4 Insight Panel

## Doel

Combineer:

* Daily summary
* Anomaly hints
* No-trade explainer

---

## UI voorbeeld

```id="z1x2c3"
Insights:

- No trades executed
- Dominant blocker: cooldown (63%)
- Compression regime dominating
- ⚠ 95% signals blocked
```

---

## Locatie

* Bovenaan pagina
* Onder health KPI

---

# 5. Architectuur

---

## Nieuwe modules

```text
services/
├── daily_summary.py
├── run_compare.py
├── anomaly_hints.py
```

---

## Dataflow

```id="v6b7n8"
JSONL → parser → summarizer → health → insights → UI
```

---

# 6. Performance regels

* Gebruik bestaande caching
* Geen extra full scans
* Werk met bestaande cap structuur
* Gebruik health_cap voor insights

---

# 7. Acceptance Criteria

Sprint C is klaar als:

## Daily summary

* verschijnt automatisch
* klopt met data

## Run comparison

* 2 runs vergelijkbaar
* verschillen zichtbaar

## Anomaly hints

* verschijnen bij edge cases
* logisch en verklaarbaar

## Insight panel

* combineert info duidelijk
* geen ruis

---

# 8. Tests

Nieuwe tests:

```text
tests/test_ops_insights.py
```

---

## Test cases

### Daily summary

* entries = 0 → “No trades”
* entries > 0 → correct aantal

---

### Anomalies

* signals > 50 + entries = 0 → detect
* regime > 80% → detect
* blocker > 80% → detect

---

### Run compare

* verschillen correct berekend
* ratios kloppen

---

# 9. Build volgorde

## Stap 1

daily_summary.py

## Stap 2

anomaly_hints.py

## Stap 3

insight panel integreren

## Stap 4

run_compare.py

## Stap 5

Run Comparison pagina

## Stap 6

tests toevoegen

---

# 10. Niet doen in Sprint C

Niet toevoegen:

* AI analyse
* complex scoring systeem
* database
* alerts
* ML

---

# 11. Definition of Done

Sprint C is klaar als:

* je opent een dag
* je ziet direct:

  * wat er gebeurde
  * waarom
  * wat opvallend is
* je kunt 2 runs vergelijken
* je weet wat je moet aanpassen

---

# 12. Mentor note

Sprint C is waar je console verandert van:

> “tool om logs te bekijken”

naar:

> **tool om beslissingen te nemen**

Dat is het verschil tussen:

* developer tooling
* trading desk tooling

---

# 13. Belangrijkste principe

```id="edge"
Edge = betere beslissingen sneller maken
```

Sprint C helpt je:

* sneller zien wat misgaat
* sneller hypotheses maken
* sneller strategie aanpassen

---

# 14. Volgende stap na Sprint C

Pas NA dit:

* alerts
* automation
* portfolio insights
* multi-account

---

# Einde Sprint C
