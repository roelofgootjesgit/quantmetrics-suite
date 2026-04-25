# Run artifact strategy

## Doel

Dit document beschrijft de strategie voor het opslaan van alle artifacts uit:

- backtests
- analytics
- guard attribution
- research logs

in één centrale, consistente structuur.

Doel:

- volledige reproduceerbaarheid  
- overzicht per experiment  
- geen losse bestanden meer verspreid over repos  

---

## Kernprincipe

```text
Alle output van een experiment hoort bij elkaar.
```

Niet verspreid over QuantBuild, QuantAnalytics en losse mappen, maar **één centrale artifact map per experiment**.

---

## Belangrijk onderscheid

### Wat we niet doen

- alle code in één map stoppen
- repos samenvoegen
- logging en analytics mengen met broncode

### Wat we wel doen

- alle **output artifacts** centraliseren
- code per repo gescheiden houden
- **QuantOS** gebruiken als orchestrator die paden en workflows uniform houdt

---

## Architectuur

```text
QuantBuild      → produceert events
QuantLog        → bewaart events
QuantAnalytics    → genereert reports
QuantResearch     → maakt beslissingen (menselijk / vastgelegd)
QuantOS           → organiseert artifacts en workflows
```

QuantOS is de plek waar **artifacts samenkomen** (niet waar trading-logica dubbel wordt gebouwd).

---

## Centrale artifact map

In QuantOS:

```text
quantmetrics_os/runs/
```

(Optioneel symlink of mounted share op VPS; inhoud is leidend, niet de exacte schijf.)

---

## Structuur per experiment

```text
runs/
  EXP-001_expansion_only/
    manifest.json

    baseline/
      run_info.json
      config_snapshot.yaml
      resolved_config.yaml
      quantlog_events.jsonl

      analytics/
        run_summary.json
        run_summary.md
        key_findings.md
        guard_attribution.json
        guard_attribution.md

    variant/
      run_info.json
      config_snapshot.yaml
      resolved_config.yaml
      quantlog_events.jsonl

      analytics/
        run_summary.json
        run_summary.md
        key_findings.md
        guard_attribution.json
        guard_attribution.md

    compare/
      guard_compare.json
      guard_compare.md

    research/
      research_log.md
      decision.json
```

Pas pad/filenames aan waar je toolchain al vaste namen heeft (bijv. `guard_attribution_<run_id>.md` uit QuantAnalytics naast `run_info.json` leggen).

---

## Config: twee snapshots (ingang vs effectief)

| Bestand | Betekenis |
| --- | --- |
| **`config_snapshot.yaml`** | Kopie van het **CLI-configpad** (`--config`). Vaak een dun bestand met `extends:` en een paar overrides (venster, artifacts, …). Handig om te zien *welk* entry-bestand je draaide. |
| **`resolved_config.yaml`** | De **effectief gemergede** runtime-config die QuantBuild gebruikt: `configs/default.yaml` + volledige `extends`-keten + env-overrides + CLI-aanpassingen (bijv. `backtest.start_date`). Dit is de **strategie-/parameter-snapshot** om runs te vergelijken, te diffen en te verbeteren. |

Gevoelige sleutels (o.a. namen met `token`, `secret`, `api_key`, …) worden in `resolved_config.yaml` naar `<redacted>` gezet; secrets horen niet in `runs/`.

Implementatie: QuantBuild schrijft tijdens artifact-collect een YAML-sidecar en `collect_run_artifact.py` kopieert die naar `resolved_config.yaml`. Zie ook `run_info.json`: velden `resolved_config` en `resolved_config_source_path`.

---

## Waarom per experiment (niet per losse run)

### Per losse run

```text
run_1/
run_2/
run_3/
```

Probleem: geen baseline/variant-relatie, vergelijken lastig.

### Per experiment

```text
EXP-001/
  baseline/
  variant/
  compare/
```

Voordeel: direct vergelijkbaar, audit-proof, één plek voor beslissing en log.

---

## Manifest

Bestand:

```text
runs/<experiment_id>/manifest.json
```

### Voorbeeldinhoud

```json
{
  "experiment_id": "EXP-001",
  "title": "Expansion-only vs baseline",
  "date": "2026-04-22",

  "baseline_run_id": "qb_run_20260422T195532Z_ac8f549c",
  "variant_run_id": "qb_run_20260422T195553Z_042ce3fe",

  "baseline_config": "configs/backtest_2026_jan_mar.yaml",
  "variant_config": "configs/backtest_2026_jan_mar_expansion_only.yaml",

  "data_window": {
    "start": "2026-01-01",
    "end": "2026-03-31"
  },

  "status": "completed",
  "decision": "promote"
}
```

---

## Wat hoort in de artifact map

### Altijd bewaren waar mogelijk

- `run_id`(s)
- **ingangs-config:** `config_snapshot.yaml` (**kopie** van het `--config`-bestand)
- **effectieve parameters:** `resolved_config.yaml` (gemergede strategie-config, secrets ge-redacted)
- QuantLog JSONL (baseline en variant elk apart)
- analytics rapporten (summary, funnel, regime, enz.)
- guard attribution (niveau A per run_id)
- guard compare output (niveau B tussen twee run_ids)
- research log + vastgelegde beslissing

### Normaal níet hier

- broncode van engines (blijft in eigen repo’s)
- tijdelijke debug dumps
- bewuste duplicaten zonder meerwaarde

---

## Workflow (QuantOS)

### Automatisering na backtest (QuantBuild)

Als in QuantBuild **`artifacts.enabled: true`** staat (in `configs/default.yaml` overrulen of via geladen config):

1. Na een succesvolle backtest + QuantAnalytics kopieert **`quantmetrics_os/scripts/collect_run_artifact.py`** naar `quantmetrics_os/runs/<experiment_id>/<role>/` onder andere:
   - `quantlog_events.jsonl` (consolidated run)
   - `config_snapshot.yaml` (kopie van het **entry**-YAML-pad uit `--config`)
   - `resolved_config.yaml` (gemergede effectieve config voor strategie/reproduceerbaarheid; optioneel `--resolved-config-yaml` vanuit QuantBuild)
   - `run_info.json` (metadata, o.a. `config_source_path`, `resolved_config`, `resolved_config_source_path`)
   - optioneel recente rapportbestanden onder **`analytics/`** (`bundle_analytics`, standaard aan)

- **`experiment_id`** — vrij te kiezen; als leeg: automatisch `EXP-YYYYMMDD-<run_suffix>`.
- **`role`** — `baseline` \| `variant` \| `single` (default `single`).
- **`quantmetrics_os_root`** — optioneel; default: sibling-map `../quantmetrics_os` naast QuantBuild.

Uitschakelen: **`artifacts.enabled: false`** of env **`QUANTMETRICS_ARTIFACTS=0`**.

---

1. **Runs uitvoeren** — QuantBuild schrijft events naar QuantLog; elk run krijgt een **`run_id`**.
2. **Analytics** — QuantAnalytics bouwt summaries en guard attribution voor elk relevant `run_id`.
3. **Artifacts verzamelen** — handmatig of via bovenstaande automatische stap naar `runs/EXP-…/baseline|variant/` inclusief **config snapshot** (`config_snapshot.yaml`) en **resolved config** (`resolved_config.yaml`).
4. **Compare** — niveau B:

```bash
quantmetrics-guard-attribution-compare \
  --baseline-run-id … \
  --variant-run-id … \
  --dir … \
  --output-dir runs/EXP-001/compare
```

(gebruik jouw echte consolidated JSONL-locatie voor `--dir` / `--jsonl`.)

5. **Research digest** — rol alle gebundelde runs op in één verslag voor QuantResearch:

```bash
cd quantmetrics_os
python scripts/research_digest.py
```

Schrijft naar **`research/runs_digest.md`** (Markdown met tabel + per-run KEY_FINDINGS) en **`research/runs_registry.json`** (machine-leesbare index). Regenereer na nieuwe bundles onder `runs/`.

**QuantOS-orchestrator:** `python quantmetrics.py backtest -c …` (vanuit `orchestrator/`) draait dit script **standaard** na een geslaagde backtest. Overslaan: `--no-research-digest`.

6. **Eigen notities** — waar nodig nog `research/research_log.md` / `research/decision.json` voor hypotheses en finale beslissing (handmatig).

---

## Belangrijkste regels

1. **Eén experiment = één map** onder `runs/`.
2. **Baseline en variant** zijn het standaard-patroon voor causal guard-attributie (losse runs alleen waar vergelijking géén doel is).
3. **`run_id`s altijd** in manifest en in research log — zonder reproduceer je niet.
4. **`config_snapshot.yaml`** (ingangs-bestand) en **`resolved_config.yaml`** (effectieve parameters) naast verwijzing naar YAML in repo waar mogelijk; git hash/commit in manifest of `run_info.json` versterkt reproduceerbaarheid verder.
5. **Strategy-wijziging pas na compare** voor guard-hypothesen — zie ook `quantanalytics/docs/GUARD_ATTRIBUTION_ENGINE.md` (niveau B leidend).

---

## Voordelen

- **Reproduceerbaarheid** — één map bevat referenties naar data, configs en outputs.
- **Auditability** — wat, wanneer, waarom, uitkomst.
- **Schaal** — later meer strategieën/markten zonder chaos in losse `output_rapport`-mappen per repo.

---

## Toekomst

- geautomatiseerde bundling vanuit QuantOS orchestrator
- CLI `quantos run-experiment` (of gelijkwaardig)
- centrale experiment registry index (`EXPERIMENT_INDEX.md` of kleine DB)

---

## Samenvatting

```text
Code blijft gescheiden per repo.
Output centraliseren onder QuantOS/runs/<experiment>.
```

Eén map per experiment, alle artifacts bij elkaar.

---

## Eindprincipe

```text
Als je een experiment niet kunt reproduceren,
kun je de edge niet verdedigen — alleen een verhaal vertellen.
```
