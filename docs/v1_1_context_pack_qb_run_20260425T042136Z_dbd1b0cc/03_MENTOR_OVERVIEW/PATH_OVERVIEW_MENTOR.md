# QuantMetrics Suite - Path Overzicht (mentor)

## Canonical workspace root

- `C:\Users\Gebruiker\quantmetrics-suite`

## Actieve sibling repositories

- `C:\Users\Gebruiker\quantmetrics-suite\quantbuild`
- `C:\Users\Gebruiker\quantmetrics-suite\quantbridge`
- `C:\Users\Gebruiker\quantmetrics-suite\quantlog`
- `C:\Users\Gebruiker\quantmetrics-suite\quantanalytics`
- `C:\Users\Gebruiker\quantmetrics-suite\quantmetrics_os`
- `C:\Users\Gebruiker\quantmetrics-suite\quantresearch` (optioneel research-/experimentworkspace)

## Canonical environment paths

- `QUANTMETRICS_OS_ROOT=C:\Users\Gebruiker\quantmetrics-suite\quantmetrics_os`
- `QUANTLOG_REPO_PATH=C:\Users\Gebruiker\quantmetrics-suite\quantlog`
- `QUANTBRIDGE_SRC_PATH=C:\Users\Gebruiker\quantmetrics-suite\quantbridge\src`
- `QUANTMETRICS_ANALYTICS_OUTPUT_DIR=C:\Users\Gebruiker\quantmetrics-suite\quantanalytics\output_rapport`

## Runtime and artifacts locations

- QuantBuild logs: `C:\Users\Gebruiker\quantmetrics-suite\quantbuild\logs`
- QuantBuild data cache: `C:\Users\Gebruiker\quantmetrics-suite\quantbuild\data\market_cache`
- QuantBuild QuantLog events (runs): `C:\Users\Gebruiker\quantmetrics-suite\quantbuild\data\quantlog_events`
- QuantAnalytics reports (los outputpad): `C:\Users\Gebruiker\quantmetrics-suite\quantanalytics\output_rapport`
- QuantOS run artifacts: `C:\Users\Gebruiker\quantmetrics-suite\quantmetrics_os\runs`

**Let op:** na een QuantOS-bundel staan de **gezaghebbende** analytics-kopieën ook onder `quantmetrics_os\runs\<experiment>\<role>\analytics\`. Het pad `output_rapport` kan aanvullende of herhaalde exports bevatten.

## Laatste gevalideerde run

- Run ID: `qb_run_20260425T042136Z_dbd1b0cc`
- Run artifact map: `C:\Users\Gebruiker\quantmetrics-suite\quantmetrics_os\runs\EXP-2025-baseline\single`
- Context pack zip: `C:\Users\Gebruiker\quantmetrics-suite\docs\v1_1_context_pack_qb_run_20260425T042136Z_dbd1b0cc.zip`
- Audit pack zip: `C:\Users\Gebruiker\quantmetrics-suite\docs\v1_1_audit_pack_qb_run_20260425T042136Z_dbd1b0cc.zip`
- Uitgepakte packs (bron voor zip): `C:\Users\Gebruiker\quantmetrics-suite\docs\v1_1_context_pack_qb_run_20260425T042136Z_dbd1b0cc\` en `...\v1_1_audit_pack_qb_run_20260425T042136Z_dbd1b0cc\`

## Policy (kort)

- We werken alleen vanuit `quantmetrics-suite` als root.
- Geen actieve legacy `*v1` lokale paden in runtime wiring.
- Suite preflight verplicht via `quantbuild/scripts/check_suite_layout.py`.

## Gerelateerde mentor-docs

- `docs/CONTEXT_PACK_MENTOR.md` — pack-index
- `docs/SYSTEM_OVERVIEW_FOR_AI_MENTOR.md` — volledig systeembeeld
