# Guard Attribution Engine

## Doel

De Guard Attribution Engine ondersteunt antwoord op:

- welke guards edge **beschermen**
- welke guards edge **blokkeren** (of schijnen te blokkeren)
- waar je **experiments** moet richten voor policy-aanpassing

Het vormt de brug tussen **QuantAnalytics** (wat gebeurde er) en **QuantResearch** (welke hypotheses test je vervolgens). QuantLog blijft de bron; deze laag leest alleen.

---

## Kernprincipe

Elke guard is een hypothese:

```text
"Deze regel voorkomt slechte trades zonder goede trades te blokkeren."
```

Guard attribution **toetst** die hypothese — niveau A als snelle indicateur, niveau B als causal check.

---

## Positie in de stack

```text
QuantBuild → QuantBridge → QuantLog → QuantAnalytics → Guard Attribution → QuantResearch
```

---

## Twee niveaus van analyse

### Niveau A — Slice counterfactual (indicatief)

**Doel:** snelle inschatting van “gemiste” kansen bij blocks.

**Werking:**

- pak `risk_guard_decision` met **BLOCK**
- trek context uit `signal_evaluated` voor dezelfde `decision_cycle_id`
- zoek uitgevoerde trades in dezelfde slice:

```text
regime | session | setup_type | signal_type | direction
```

- gebruik het **gemiddelde `pnl_r`** van die slice als schatting (`estimated_r`)

**Voorbeeld**

- Block-context: expansion, NY, SQE-setup  
- Slice van uitgevoerde trades in die slice: mean R = **+0.42**  
→ voor die block-rij: **estimated_r ≈ +0.42** (mits voldoende slice-sample; anders fallback en `fallback_used`)

**Beperkingen**

- gevoelig voor kleine samples  
- **niet causaal**  
- alleen **richting** voor onderzoeksplan (hypothese), geen definitieve policy-beslissing

---

### Niveau B — Rerun compare (causaal, leidend)

**Doel:** echte impact van **één** guard-/filterwijziging meten.

**Werking:**

```text
Baseline → guard/policy zoals nu
Variant  → alleen die guard OFF / relaxed / andere threshold
```

Vergelijk onder andere:

```text
Δ trades   Δ mean R   Δ sum R   Δ drawdown (R-pad)   Δ PF (benaderend)
Δ BLOCK-count per guard
```

**Waarheid:** slice = indicatie · rerun = beslissing.

**Advies**

- niveau A: prima om `likely_overblocking` te zien als **startpunt**
- **strategy-keuzes**: pas vastleggen als niveau B de hypothesen **bekrachtigt of weerspreekt**

---

## Dataflow

### Input (QuantLog events)

Nodig voor de geïmplementeerde tooling:

- `signal_evaluated`
- `risk_guard_decision`
- `trade_closed`

Optioneel breder funnel-onderzoek:

- `trade_action`

---

### Output (logical / JSON-inhoud)

Conceptueel komen deze tabellen terug in de rapport-JSON (niet per se als apart Parquet-bestand):

| Concept | Betekenis |
|---------|-----------|
| guard blocks | 1 rij per BLOCK; velden o.a. `run_id`, `decision_cycle_id`, `guard_name`, context (regime, session, setup, signal, direction) |
| executed trades | uit `trade_closed`; aanvulling setup/signal via join op gezamenlijke `decision_cycle_id` waar mogelijk |
| counterfactual estimates | per block: `estimated_r`, sample / fallback flags |

**Artefacten op schijf**

```text
output_rapport/guard_attribution_<run_id>.json
output_rapport/guard_attribution_<run_id>.md

output_rapport/guard_attribution_compare_<baseline>_vs_<variant>.json
output_rapport/guard_attribution_compare_<baseline>_vs_<variant>.md
```

---

## Guard scorecard (niveau A)

Per guard (samengevat in JSON/MD):

- block count · share of blocks  
- geschatte missed winners / avoided losers (slice-benadering)  
- net block value (conceptueel: avoided losses − missed winners in R-eenheden)  
- **assessment**

### Assessment labels

- `likely_overblocking`
- `likely_protective`
- `inconclusive`

### Beslisregels (eerste versie, heuristisch)

| Situatie | Lezing |
|----------|--------|
| veel blocks + positieve gemiddelde `estimated_r` + voldoende slice-data | neiging tot **overblocking** — waard om met B te testen |
| negatieve gemiddelde `estimated_r` | neiging **protective** |
| kleine slice of veel fallback | **inconclusive** — niet hard concluderen |

---

## Rerun compare — interpretatie (niveau B)

### Positief signaal (guard versoepelen overwegen)

Variant toont o.a.:

- trades ↑  
- mean R **gelijk of licht** lager  
- sum R ↑  
- DD **acceptabel** t.o.v. risicobudget  

### Negatief signaal (guard behouden)

Variant toont o.a.:

- trades ↑ maar mean R **sterk** ↓  
- DD **sterk** ↑  

### Ideaal voor schaal (hypothese)

- trades ↑ · mean R blijft **positief** · sum R ↑ · DD **gecontroleerd**

Alle uitspraken blijven gekoppeld aan **getallen** in het compare-rapport; geen oordeel zonder metrics.

---

## Workflow

1. **Analyse A** — `quantmetrics-guard-attribution --run-id …`  
   Dominante guards en eerste inschatting.

2. **Hypothese** — bv. *`regime_profile` blokkeert te veel winst in expansion + NY*.

3. **Rerun B** — twee QuantBuild-runs: baseline vs variant (**één verschil**).

4. **Compare** — `quantmetrics-guard-attribution-compare --baseline-run-id … --variant-run-id …`

5. **Beslissing** — keep · relax · redesign · remove (documenteren met run_ids).

---

## Regels

- **Altijd één guard/config-verschil** per experiment (geen combo’s).
- **Zelfde dataset/window** (symbol, timeframe, datums).
- **Altijd baseline vs variant** gelabeld; `run_id`s in je **research log**.
- Geen harde productie-conclusie op **slice alleen**.
- Slice zegt **waar je moet kijken**; rerun compare zegt **wat je onderzoeks-wise doet**.

---

## Experimentdiscipline (causaliteit)

Voor een geldige compare:

1. Exact **één** verschil tussen baseline en variant.  
2. **Zelfde venster** en waar mogelijk dezelfde cache/build.  
3. Labels expliciet (`--baseline-label` / `--variant-label`, plus config-/commit-naam).  
4. **`run_id`s vastleggen** zodat resultaten reproduceerbaar zijn.

Anders vervuilt het effect en kun je geen guard toeschrijven.

---

## Prioriteit guards (richting voor dit systeem)

1. **`regime_profile`** — Vaak groot aandeel in blocks; direct gekoppeld aan regime-edge.  
2. **`regime_allowed_sessions`** — Session-gating vs edge in specifieke sessies.  
3. **`daily_loss_cap`** — Risico-afkapping; kan throughput en DD vervormen in discovery-runs.

---

## MVP-status (repo)

- Block-extractie en contextaggregatie  
- Slice-counterfactual + scoring  
- Rerun compare + Δ-metrics en guard-block-tabellen  
- CLI: `quantmetrics-guard-attribution`, `quantmetrics-guard-attribution-compare`

### Mogelijke uitbreidingen

- experiment-registry / automatische logging naar QuantResearch  
- confidence per guard · multi-run aggregatie · charts  

---

## Samenvatting

```text
Slice-analyse zegt waar je moet kijken.
Rerun compare zegt wat je moet doen (onderbouwd met realized metrics).
```

**Einddoel:** van “guards blokkeren trades” naar **bewuste optimalisatie van edge** — eerst meten (B), dan wijzigen.
