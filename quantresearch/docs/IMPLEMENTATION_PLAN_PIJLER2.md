# Implementatieplan Pijler 2 — Inferentie op Per-Trade R

Dit document is de canonieke beschrijving van Pijler 2 (inferentielaag op per-trade R). Aanvullende repo-notities staan onderaan.

## Architectuuroverzicht

```
QuantBuild (backtest)
    → JSONL: trade_closed.payload.pnl_r
    → (fallback) {run_id}_trade_r_series.json als quantlog.enabled false

QuantAnalytics (meting)
    → leest R-lijst uit JSONL of *_trade_r_series.json
    → schrijft {run_id}_inference_report.json naar output_rapport/

collect_run_artifact.py (transport)
    → kopieert inference-rapport naar analytics/inference_report.json in de bundle

QuantResearch (governance)
    → leest experiments/<id>/inference_report.json (of QuantOS-bundle)
    → vult academic_status / effective_status (optioneel via manifest)
```

## Stap 0 — QuantBuild: Policy + Fallback Export

**Policy** (`quantbuild/configs/default.yaml` onder `quantlog:`):

- `enabled` — zoals bestaand.
- `inference_requires_quantlog` — wanneer `true` en `enabled: false`, faalt `run_backtest` met een duidelijke `ValueError` (inferentie-officiële runs moeten JSONL kunnen reproduceren). Standaard in repo: `false` zodat snelle subprocessen (o.a. HYP-002 metrics-only) niet breken; zet op `true` voor strikte inference-runs.

**Fallback export** (`quantbuild/src/quantbuild/export/trade_r_series.py`):

- `write_trade_r_series(trades, trade_refs, run_id, output_dir)` schrijft `{run_id}_trade_r_series.json` onder hetzelfde pad als geconsolideerde runs (`quantlog.base_path/runs/`).
- `trade_refs` parallel aan `trades` (zelfde volgorde als `trade_closed` / `Trade`-lijst); `Trade` heeft geen `trade_id` in het model — refs komen uit de backtest (`BT-{trace[:8]}`).

**Aanroep:** aan het einde van de backtest-loop wanneer `quantlog.enabled` false is en er trades zijn.

**Tests:** (1) JSONL `pnl_r`-volgorde gelijk aan `Trade.profit_r` bij quantlog aan; (2) bij quantlog uit: fallbackbestand aanwezig en `pnl_r`-reeks gelijk aan returned trades.

## Stap 1 — QuantAnalytics: Inference Module

**Modules:**

- `quantmetrics_analytics/analysis/inference_engine.py` — Shapiro (n ≤ 5000), Wilcoxon signed-rank vs `h0_median` tenzij normaliteit p > 0.05 → `ttest_1samp`; bootstrap 95% CI (BCa via `scipy.stats.bootstrap`); Cohen’s d; verdicts `PASS` / `FAIL` / `INSUFFICIENT_N`.
- `quantmetrics_analytics/analysis/inference_report.py` — serialisatie `schema_version: inference_v1`.

**Economische significantie (contract):**

- **Oud (verwijderd):** `econ_verdict = "PASS"` als `mean_r >= minimum_effect_size_r` (puntgemiddelde — te zwak voor een economische claim).
- **Nieuw:** `econ_verdict = "PASS"` als **`ci_95_lower >= minimum_effect_size_r`** (ondergrens van het 95%-bootstrap-CI op het gemiddelde van per-trade R). Zelfde regel staat expliciet in `inference_report.json` onder **`verdict.economic_rule`** en in `confidence_interval.lower` / **`ci_95_lower`**.

**CLI:** `--reports inference` (niet in default `all`, om scipy zwaarte te vermijden). Optioneel `--experiment-id`, `--bootstrap-tier standard|high`, `--inference-require-jsonl` (faal als alleen fallback-R gebruikt wordt).

**Dependencies:** `scipy`, `numpy` in `quantanalytics/pyproject.toml`.

## Stap 2 — collect_run_artifact.py

- Bestanden die matchen op `*_inference_report.json` worden naar `analytics/inference_report.json` gekopieerd (canonieke bundelnaam; `run_id` blijft in het JSON).

## Stap 3 — QuantResearch: Consumption Layer

- `quantresearch/inference_consumer.py` — `load_inference_report`, `apply_inference_to_experiment` (vergelijkt JSON met pre-reg gates; **economische gate = `confidence_interval.lower` (of `ci_95_lower`) t.o.v. `minimum_effect_size_r`**, niet het puntgemiddelde en niet blind het veld `verdict.economic_significance` voor de beslissing).
- `pipelines/hyp002_promotion_bundle.json`: optioneel `"inference_consumer": true` — als `experiments/EXP-002/inference_report.json` bestaat, worden statusvelden bijgewerkt; ontbreekt het bestand → geen fout, status blijft zoals zonder inferentie.

## Testplan (samenvatting)

| Laag | Test |
|------|------|
| QuantBuild | R-lijst JSONL vs trades; fallback JSON vs trades |
| QuantAnalytics | Wilcoxon/INSUFFICIENT_N/bootstrap smoke; schema velden; CI-ondergrens vs economische drempel |
| QuantResearch | apply_inference gate-logica (o.a. hoog mean maar lage `ci_95_lower` → FAIL); optionele consumer |

## Repo-specifieke aanscherpingen

1. **Trade-model:** geen `trade_id` op `Trade`; gebruik parallelle `trade_refs` (zie Stap 0).
2. **Toetskeuze:** Shapiro-gestuurde keuze Wilcoxon vs t is expliciet in het rapport vastgelegd (`hypothesis_test.test_used`); zie `ACADEMIC_RESEARCH_PROTOCOL.md` voor interpretatie vs strikte pre-reg.
3. **collect_run_artifact:** vereist nog steeds geconsolideerde JSONL voor de bestaande bundle-flow; inferentie is een extra analytics-artefact.
4. **HYP-002 pipeline-subprocess:** zet `quantlog.enabled` uit; houd `inference_requires_quantlog` uit of expliciet `false` in die snippet.

## Implementatievolgorde

1. Stap 0 + tests  
2. Stap 1 engine + tests + CLI + report  
3. Stap 2 collect script  
4. Stap 3 consumer + manifest-hook  

---

*Versie: 2 — economische gate op CI-ondergrens (mei 2026).*
