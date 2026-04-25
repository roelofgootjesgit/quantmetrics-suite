# QuantMetrics Suite — systeemoverzicht (AI mentor)

Dit document beschrijft de **huidige** end-to-end opzet van `quantmetrics-suite` zoals die in de monorepo staat. Het is bedoeld als **één leesbare laag** naast het context pack (structuur) en het audit pack (run-bewijs).

## Doel van de suite

De suite koppelt **beslissing** (signalen, guards, regime), **event-integriteit** (QuantLog), **orchestratie van runs** (QuantOS) en **post-trade uitleg** (QuantAnalytics). Het doel is reproduceerbare besliskwaliteit te meten — niet alleen PnL te tonen.

## Keten (data en verantwoordelijkheid)

```text
Marktdata → quantbuild (beslislogica, backtest/live pad) → quantlog (JSONL events)
         → quantmetrics_os (run-bundel: config + events + analytics-kopie)
         → quantanalytics (read-only rapporten, guards, funnel)
         → quantresearch (optioneel: experimenten, dossiers, ledger)
quantbridge voert orders uit wanneer live/paper; in backtest blijft execution gesimuleerd in quantbuild.
```

| Laag | Pad | Rol |
|------|-----|-----|
| Decision | `quantbuild/` | Strategie, regime, risk guards, backtest-engine, `trade_action` / funnel-events |
| Execution | `quantbridge/` | Broker-adapters, order lifecycle (naast backtest) |
| Observability | `quantlog/` | Schema, validatie, JSONL (append-only waar van toepassing) |
| Orchestratie | `quantmetrics_os/` | `runs/<experiment>/<role>/`: `config_snapshot.yaml`, `quantlog_events.jsonl`, `analytics/` |
| Analyse | `quantanalytics/` | O.a. key findings, guard attribution, edge reports (input = event-export) |
| Research | `quantresearch/` | Experimentregistry, dossiers, vergelijking (optioneel) |

Canonical namen en grenzen staan in `docs/SYSTEM_CANONICAL_STRUCTURE.md`.

## Belangrijke paden op deze workspace

- **Suite root:** `quantmetrics-suite/`
- **Run-artifacts (voorbeeld):** `quantmetrics_os/runs/EXP-2025-baseline/single/`
- **QuantBuild events (bron tijdens run):** `quantbuild/data/quantlog_events/runs/<run_id>.jsonl` (consolidated run file kan via config)
- **Losse analytics-output (optioneel):** `quantanalytics/output_rapport/` — kan kopieën bevatten naast de bundle onder QuantOS

Zie ook `docs/PATH_OVERVIEW_MENTOR.md` voor omgevingsvariabelen en logmappen.

## Eén gevalideerde referentierun

- **Run ID:** `qb_run_20260425T042136Z_dbd1b0cc`
- **Experiment:** `EXP-2025-baseline`, rol `single`
- **Config-ingang:** `quantbuild/configs/backtest_2025_full_strict_prod.yaml` (snapshot in de run-map als `config_snapshot.yaml`)
- **Venster / intentie:** kalenderjaar 2025 met dezelfde SQE/regime-profielen als `strict_prod_v2` (zie commentaar in `config_snapshot.yaml`)

De bijbehorende **audit pack** bevat config, event-sample, analytics-tekst, key findings en een **analytics_bundle** (o.a. edge verdict, promotion decision, CSV/JSON). De **context pack** bevat canonical structuur en actuele module-README’s.

## Mentor-packs (hoe ze te gebruiken)

| Pack | Locatie (map + zip onder `docs/`) | Gebruik |
|------|-------------------------------------|---------|
| **Context pack** | `docs/v1_1_context_pack_qb_run_20260425T042136Z_dbd1b0cc/` en `.zip` | Architectuur, grenzen, naming, module-identiteit |
| **Audit pack** | `docs/v1_1_audit_pack_qb_run_20260425T042136Z_dbd1b0cc/` en `.zip` | Run-bewijs: exacte config, events, analytics-output, relevante decision-engine bron-snapshots |

Korte index: `docs/CONTEXT_PACK_MENTOR.md`. Paden: `docs/PATH_OVERVIEW_MENTOR.md`.

## Operationele afspraken

- Werk vanuit **één suite-root**; preflight/layout-check: `quantbuild/scripts/check_suite_layout.py` (zie module-docs).
- **Geen** runtime-identiteit met versie-suffixen zoals `*v1` in paden; versie zit in git/schema.
- `config_snapshot.yaml` in een run is de **CLI-ingang**; voor volledige effectieve parameters kan `resolved_config.yaml` (indien aanwezig) leidend zijn voor diffs — zie `quantmetrics_os/docs/RUN_ARTIFACT_STRATEGY.md`.

## Wat de AI mentor hiermee moet kunnen

1. **Structuurvragen** → context pack + `SYSTEM_CANONICAL_STRUCTURE.md`.
2. **“Bewijs: wat gebeurde er in run X?”** → audit pack `04_RUNTIME_EXAMPLE/` + `03_CONFIGS/`.
3. **“Waarom blokkeerden guards?”** → `analytics_bundle/guard_attribution.json`, key findings, `EDGE_REPORT.md` / `PROMOTION_DECISION.md` in de bundle.
4. **Codepad beslissing** → audit pack `05_DECISION_ENGINE/` (snapshots; echte module staat onder `quantbuild/src/quantbuild/`).

---

*Document bijgewerkt samen met pack-refresh (events/config/analytics/module-README’s gesynchroniseerd met de repo-state rond EXP-2025-baseline).*
