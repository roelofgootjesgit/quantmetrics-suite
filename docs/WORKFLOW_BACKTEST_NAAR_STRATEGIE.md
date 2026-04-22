# Handleiding: workflow van backtest naar strategy (QuantResearch)

Deze handleiding beschrijft **hoe je de research-workflow aanzet**: van twee (of meer) backtest-runs in **QuantBuild** tot een **traceerbare beslissing** die je strategy-iteratie voedt. De beslislaag leeft in **QuantResearch** (lokaal: `quantresearch`; remote kan bijvoorbeeld [QuantResearch-Decision-Engine](https://github.com/roelofgootjesgit/QuantResearch-Decision-Engine.git) zijn).

---

## 1. Wat we willen bereiken

| Fase | Laag | Output |
|------|------|--------|
| Backtest | QuantBuild | Trades + metrics (YAML/config + datawindow vast) |
| Interpretatie (optioneel) | QuantAnalytics | Samenvattingen, slices (regime/session), key findings |
| Hypothese & besluit | QuantResearch | `experiments.json`, vergelijking, research log, edges/rejects |

**Kernregel:** geen strategy-wijziging “op gevoel”: elke wijziging hoort bij minstens één **experiment** met **baseline-run**, **variant-run**, **zelfde datawindow**, en **run_id**’s die naar concrete artifacts verwijzen.

---

## 2. Rollen in de stack (kort)

```text
QuantBuild     → simulatie / metrics
QuantBridge    → live execution (run_id in events)
QuantLog       → bron van waarheid (JSONL, append-only)
QuantAnalytics → “what happened” (aggregatie op events / exports)
QuantResearch  → “what it means” + besluit + knowledge base
```

Voor **puur backtest-gedreven** research volstaat vaak: QuantBuild-metrics (JSON) → QuantResearch. Zodra je live/paper vergelijkt, komen QuantLog + QuantAnalytics structureel mee (zie analytics-handboek in `quantanalyticsv1`).

---

## 3. Voor je start (checklist)

- [ ] **Eén hypothese per experiment** (bijv. alleen “expansion-only vs baseline”, niet tegelijk session + guard).
- [ ] **Zelfde symbol/timeframe en datawindow** voor baseline en variant.
- [ ] **Baseline-config** is vast (prod-achtig of afgesproken referentie).
- [ ] **Variant-config** wijzigt precies het stuk dat de hypothese test.
- [ ] Je noteert of genereert twee **run_id**’s (zie §4) en bewaart de **metrics-JSON** (of analytics-export) per run.

---

## 4. Run_id’s en artifacts

QuantResearch verwacht **strings** `baseline_run_id` en `variant_run_id` die uniek een run identificeren.

**Aanbevolen (backtest):** UTC-timestamp compact, bijvoorbeeld `20260422_192631Z` (zoals in je experiment-spec).  
Belangrijk is **consistentie**: dezelfde id staat in `registry/experiments.json`, in de research log, en in bestandsnamen van exports.

**Metrics voor de comparison engine:** JSON met kernvelden die QuantBuild al kent of die je mapt, bijvoorbeeld:

- `trade_count` / `total_trades`
- `mean_r` / `expectancy_r`
- `winrate` / `win_rate_raw`
- optioneel: `avg_mae_r`, `avg_mfe_r`, `drawdown`, `profit_factor`, flow/blockvelden

De Python-laag normaliseert veel aliassen (zie `quantresearch/metrics_normalize.py`).

---

## 5. Stappenplan: backtest → QuantResearch → strategy-besluit

### Stap A — Experiment vastleggen in de registry

1. Open `registry/experiments.json` (of gebruik de API: `upsert_experiment` uit `quantresearch.experiment_registry`).
2. Maak een record met status **`planned`**: titel, hypothese, `baseline_config`, `variant_config`, `data_window`, `strategy_version`, tags.
3. Ken **`experiment_id`** toe (`EXP-001`, …) of laat de registry een volgnummer voorstellen.

### Stap B — Baseline-backtest draaien (QuantBuild)

1. Kies je baseline-YAML (zelfde start/end als variant).
2. Draai je gebruikelijke backtest (CLI of script).
3. Exporteer of kopieer **metrics naar één JSON-bestand**, bijvoorbeeld `artifacts/20260422_192631Z_baseline.json`.  
   - Als je al een bestand zoals `reports/latest/strategy_variants.json` hebt met meerdere varianten, knip voor QuantResearch **één object** of één subset eruit zodat je twee platte metric-dicts hebt.

### Stap C — Variant-backtest

1. Pas alleen de strategy-interventie aan die bij de hypothese hoort.
2. Zelfde datawindow als baseline.
3. Sla metrics op als tweede JSON, gekoppeld aan `variant_run_id`.

### Stap D — QuantAnalytics (aanbevolen zodra het kan)

1. Genereer run-samenvatting / slices (regime, session, setup) volgens jullie analytics-pipeline.
2. Gebruik die output om **sectie “Analyse”** in de research log te onderbouwen (cijfers eerst, dan interpretatie).

### Stap E — Vergelijking (QuantResearch)

Vanaf de repo-root (of met `QUANTRESEARCH_ROOT` gezet naar die root):

```python
from pathlib import Path
from quantresearch.comparison_engine import (
    compare_runs,
    write_comparison_artifacts,
    load_json_metrics,
)

baseline = load_json_metrics(Path("pad/naar/baseline_metrics.json"))
variant = load_json_metrics(Path("pad/naar/variant_metrics.json"))

cmp = compare_runs(
    baseline,
    variant,
    experiment_id="EXP-001",
    baseline_run_id="20260422_192631Z",
    variant_run_id="20260422_192633Z",
)
write_comparison_artifacts(cmp)
```

Resultaat: `comparisons/EXP-001_comparison.json` en `.md` met delta + **automatische decision hint** (rule-based).

### Stap F — Research log (mens-leesbaar)

Gebruik `quantresearch.research_log_builder`:

- Vul meta + hypothese + interventie + verwachting + (handmatig) analyse/conclusie/beslissing/volgende stap.
- Schrijf naar `research_logs/YYYY-MM-DD_EXP-XXX_korte_naam.md` (zie `build_research_log_markdown` / `write_research_log`).

### Stap G — Besluit en knowledge base

1. Update het experiment in `experiments.json`: `status` (`completed` / `rejected` / `promoted`), `result` (`positive` / `negative` / `inconclusive`), `decision` (vrije tekst, bijv. `promote_for_next_research_stage`).
2. Bij bevestigde of verworpen kennis: `registry/confirmed_edges.json` en/of `registry/rejected_hypotheses.json` (of API `edge_registry.add_edge_record` / `add_rejected_hypothesis`).

### Stap H — Strategy-aanpassing (pas hier pas code/YAML)

- **Promote:** variantconfig (of delen ervan) mergen naar “next stage” (paper, subset live, of hoofdbranch) volgens jullie release-discipline.
- **Reject:** geen merge; noteer geleerde les in rejected hypotheses.
- **Inconclusive:** geen strategy-besluit; nieuw experiment ontwerpen (kleinere scope of meer data).

### Stap I — Research index (README)

```python
from quantresearch.markdown_renderer import write_readme

write_readme(
    open_questions=["..."],
    next_experiments=["EXP-002 ..."],
)
```

Dit overschrijft `README.md` met een actuele tabel + lijsten.

---

## 6. Koppelen aan GitHub (`QuantResearch-Decision-Engine`)

De remote [https://github.com/roelofgootjesgit/QuantResearch-Decision-Engine.git](https://github.com/roelofgootjesgit/QuantResearch-Decision-Engine.git) kun je als **centrale plek** voor registry + logs + comparisons gebruiken.

```bash
cd c:\Users\Gebruiker\quantresearch
git remote add origin https://github.com/roelofgootjesgit/QuantResearch-Decision-Engine.git
git add .
git commit -m "Initial QuantResearch workflow and registries"
git branch -M main
git push -u origin main
```

*(Als `origin` al bestaat, gebruik `git remote set-url origin ...`.)*

**Let op:** grote binaire backtest-exports hoeven **niet** in deze repo; commit vooral JSON/markdown die onderzoek reproduceerbaar maken, en verwijs in het experiment-record naar waar de ruwe runs staan.

---

## 7. Typische fouten (vermijden)

| Fout | Gevolg |
|------|--------|
| Andere datawindow baseline vs variant | Oneerlijke vergelijking |
| Geen baseline | Geen causal “wat veranderde?” |
| Meerdere hypotheseknoppen tegelijk togglen | Onduidelijk welke wijziging effect had |
| Alleen markdown, geen registry-update | Niet traceerbaar voor het team |
| Alleen gevoel in conclusie | Geen herleiding naar metrics |

---

## 8. Samenvatting

1. **Registry** → experiment gepland.  
2. **QuantBuild** → baseline + variant metrics, vaste window, twee **run_id**’s.  
3. **QuantAnalytics** (optioneel maar waardevol) → slices en interpretatie.  
4. **QuantResearch** → compare, logs, besluit, edges/rejects, README.  
5. **Strategy** → pas na expliciete beslissing (promote/reject/meer testen).

Zo zet je de workflow **structureel** aan van backtesten naar strategy, met reproduceerbare research in plaats van losse notities.
