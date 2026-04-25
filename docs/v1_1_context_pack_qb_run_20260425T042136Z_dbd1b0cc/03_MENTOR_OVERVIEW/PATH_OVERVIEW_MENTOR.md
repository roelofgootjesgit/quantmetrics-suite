# QuantMetrics Suite - Path Overzicht (mentor)

## Canonical workspace root

- `C:\Users\Gebruiker\quantmetrics-suite`

## Actieve sibling repositories

- `C:\Users\Gebruiker\quantmetrics-suite\quantbuild`
- `C:\Users\Gebruiker\quantmetrics-suite\quantbridge`
- `C:\Users\Gebruiker\quantmetrics-suite\quantlog`
- `C:\Users\Gebruiker\quantmetrics-suite\quantanalytics`
- `C:\Users\Gebruiker\quantmetrics-suite\quantmetrics_os`

## Canonical environment paths

- `QUANTMETRICS_OS_ROOT=C:\Users\Gebruiker\quantmetrics-suite\quantmetrics_os`
- `QUANTLOG_REPO_PATH=C:\Users\Gebruiker\quantmetrics-suite\quantlog`
- `QUANTBRIDGE_SRC_PATH=C:\Users\Gebruiker\quantmetrics-suite\quantbridge\src`
- `QUANTMETRICS_ANALYTICS_OUTPUT_DIR=C:\Users\Gebruiker\quantmetrics-suite\quantanalytics\output_rapport`

## Runtime and artifacts locations

- QuantBuild logs: `C:\Users\Gebruiker\quantmetrics-suite\quantbuild\logs`
- QuantBuild data cache: `C:\Users\Gebruiker\quantmetrics-suite\quantbuild\data\market_cache`
- QuantBuild QuantLog events: `C:\Users\Gebruiker\quantmetrics-suite\quantbuild\data\quantlog_events`
- QuantAnalytics reports: `C:\Users\Gebruiker\quantmetrics-suite\quantanalytics\output_rapport`
- QuantOS run artifacts: `C:\Users\Gebruiker\quantmetrics-suite\quantmetrics_os\runs`

## Laatste gevalideerde run

- Run ID: `qb_run_20260425T042136Z_dbd1b0cc`
- Run artifact map: `C:\Users\Gebruiker\quantmetrics-suite\quantmetrics_os\runs\EXP-2025-baseline\single`
- Audit zip (v1.1): `C:\Users\Gebruiker\quantmetrics-suite\v1_1_audit_pack_qb_run_20260425T042136Z_dbd1b0cc.zip`

## Policy (kort)

- We werken alleen vanuit `quantmetrics-suite` als root.
- Geen actieve legacy `*v1` lokale paden in runtime wiring.
- Suite preflight verplicht via `quantbuild/scripts/check_suite_layout.py`.
