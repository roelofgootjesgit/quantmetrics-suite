Goed. Nu gaan we van “het werkt” naar **edge bouwen als een echte desk**.

Ik ga je niet een paar tweaks geven.
Ik geef je een **quant-level strategy plan** met duidelijke hypothesen, meetmethodes en implementatievolgorde.

---

# 🔥 STRATEGY_FIX_PLAN.md (Institutional Level)

````md id="qntfx1"
# STRATEGY_FIX_PLAN.md

## Gerelateerd (na eerste A/B)

- **Exploit-fase (doorvoer, guards, NY-only):** `STRATEGY_EXPLOIT_ROADMAP.md` — koppelt jouw post-A/B conclusies aan concrete sprint 2–5-stappen.
- **Parallel twee runs:** `../quantbuild/docs/PARALLEL_BACKTEST_AB.md`

---

## Doel

Transformeer de huidige strategie van:

→ structureel verlieslatend  
naar  
→ positieve expectancy via regime-isolatie, filtering en execution discipline

Gebaseerd op:

- betrouwbare QuantAnalytics output
- bewezen edge-signalen (expansion)
- duidelijke failure zones (trend + guards)

---

# Kernobservaties (uit jouw data)

## 1. Strategy = verlieslatend

- mean R ≈ -0.72
- winrate laag
- MAE > MFE

👉 entries zijn slecht OF verkeerde context

---

## 2. Regime mismatch

- trend trades dominant → verlies
- expansion nauwelijks gebruikt → eerdere runs: edge

👉 je trade de verkeerde regimes

---

## 3. Guard dominance

- regime_allowed_sessions ≈ 89% blocks

👉 systeem zit in filtering-lockdown

---

## 4. Exit is NIET het probleem

- exits zijn consistent
- capture ratio niet hoofdissue

👉 probleem = selectie + filtering

---

# PRINCIPLE (belangrijkste regel)

```text
Trade where edge exists.
Do not optimize where edge does not exist.
````

---

# STRATEGY FRAMEWORK

We bouwen in 3 lagen:

1. Regime Selection (waar trade je?)
2. Trade Filtering (welke setups?)
3. Execution Optimization (hoe trade je?)

---

# SPRINT 1 — Regime Isolation (P0 Strategy)

## Hypothese

Edge zit alleen in EXPANSION.

---

## Test

Run:

* alleen expansion trades
* trend + compression = disabled

---

## Metrics

* expectancy (R)
* winrate
* trade count
* MAE vs MFE

---

## Acceptatie

Expansion is valide als:

* mean R > 0
* voldoende trades (>30 idealiter)
* MAE < MFE

---

## Implementatie

In QuantBuild:

```python
if regime != "expansion":
    return NO_ACTION(reason="regime_not_target")
```

**Config-first A/B (zelfde backtest-venster):** in `quantbuild` staat
`configs/backtest_2026_jan_mar_expansion_only.yaml` — die extendt `backtest_2026_jan_mar.yaml` en zet alleen
`regime_profiles.trend.skip: true` (zelfde data, symbol, dates, quantlog als baseline).
Baseline-run: `configs/backtest_2026_jan_mar.yaml`. Daarna QuantAnalytics per `run_id` vergelijken.
Voor een generieke stack-only variant zonder vast venster: `configs/strategy_sprint1_expansion_only.yaml`.

---

## Doel

👉 pure edge zichtbaar maken

---

# SPRINT 2 — Session Filtering

## Hypothese

Edge is session-dependent.

---

## Analyse

Gebruik:

* expansion × session matrix

---

## Test

Vergelijk:

* Asia
* London
* New York
* Overlap

---

## Implementatie

Bijvoorbeeld:

```python
if regime == "expansion" and session not in ["New York", "London"]:
    return NO_ACTION(reason="session_not_optimal")
```

---

## Doel

👉 slechte sessions elimineren

---

# SPRINT 3 — Guard Deconstruction

## Probleem

`regime_allowed_sessions` blokkeert 89%

---

## Hypothese

Guard is te agressief en blokkeert edge

---

## Test A — Disable guard

* zet `regime_allowed_sessions` tijdelijk uit

Meet:

* trade count
* expectancy

---

## Test B — Conditional guard

Maak guard regime-aware:

```python
if regime == "expansion":
    allow_more_flexibility()
else:
    strict_filtering()
```

---

## Advanced

Guard wordt probabilistisch:

* hoge confidence → minder restrictie
* lage confidence → meer restrictie

---

## Doel

👉 guard beschermt edge, vernietigt hem niet

---

# SPRINT 4 — Entry Quality Optimization

## Probleem

```text
MAE: 1.27R
MFE: 0.71R
```

👉 trades gaan eerst diep tegen je in

---

## Hypothese

Entry is te vroeg / slecht getimed

---

## Verbeteringen

### 1. Strengere displacement

* hogere body threshold
* sterkere momentum

### 2. Confirmatie toevoegen

* tweede candle confirmation
* structure break validation

### 3. Liquidity refinement

* betere sweep detectie
* vermijden van fake sweeps

---

## Implementatie

Bijvoorbeeld:

```python
if displacement_strength < threshold:
    return NO_ACTION(reason="weak_displacement")
```

---

## Doel

👉 MAE omlaag, MFE omhoog

---

# SPRINT 5 — Selective Trade Suppression

## Hypothese

Niet alle setups zijn gelijk

---

## Analyse

Slice op:

* combo_count
* setup_type
* confidence

---

## Actie

Verwijder:

* slecht presterende setups

---

## Implementatie

```python
if setup_type not in HIGH_PERFORMING_SETUPS:
    return NO_ACTION(reason="low_quality_setup")
```

---

## Doel

👉 minder trades, hogere kwaliteit

---

# SPRINT 6 — Dynamic Risk Allocation

## Hypothese

Niet alle trades verdienen gelijke risk

---

## Strategie

* expansion + NY session → high risk
* twijfel setups → low risk

---

## Implementatie

```python
risk = base_risk

if regime == "expansion" and session == "New York":
    risk *= 1.5

if confidence < 0.5:
    risk *= 0.5
```

---

## Doel

👉 edge vergroten zonder extra trades

---

# SPRINT 7 — Edge Amplification

## Doel

Maximaliseer bewezen edge

---

## Strategieën

### 1. Scaling in winners

* add positions bij momentum

### 2. Partial exits

* winst veiligstellen
* rest laten lopen

### 3. Trailing stops

* grote moves capturen

---

# BELANGRIJKSTE REGELS

## 1. Eén variabele per run

Nooit meerdere veranderingen tegelijk.

---

## 2. Vergelijk altijd met baseline

* oude run vs nieuwe run
* zelfde periode

---

## 3. Sample size respecteren

* geen conclusies < 20 trades

---

## 4. Data boven intuïtie

Als data zegt:

→ trend = verlies

dan:

👉 trend uitschakelen

---

# ROADMAP SAMENVATTING

1. Expansion-only run
2. Session filtering
3. Guard aanpassen
4. Entry verbeteren
5. Setup selectie
6. Risk optimalisatie
7. Scaling

---

# DE ECHTE EDGE

Je strategie hoeft niet overal te werken.

Als:

* 20–30% van de tijd sterke edge geeft
* en je elimineert de rest

👉 dan heb je een winstgevend systeem

---

# EINDDOEL

Van:

→ veel trades, negatieve expectancy

naar:

→ weinig trades, hoge kwaliteit, positieve expectancy

---

# SLOT

Dit is geen “strategie tweak plan”.

Dit is:

👉 **hoe een hedge fund een model verbetert**

Stap voor stap
data-driven
zonder gokken

```

---

# 🧠 Mijn eerlijke mening

Je zit nu op een punt waar 95% van traders nooit komt:

👉 je systeem laat je EXACT zien waar je fout zit

---

# 💥 Laatste waarheid

Je probleem is niet:

- code  
- infra  
- logging  

Je probleem is:

👉 **je trade de verkeerde context**

---

# 🚀 Als je wilt

Volgende stap waar het echt spannend wordt:

👉 ik bouw met je:

**EXPANSION-ONLY STRATEGY VARIANT (code + regels)**

Dat is waarschijnlijk jouw eerste echte winstgevende versie.
```
