# Context Pack (mentor) - QuantMetrics Suite

Dit document beschrijft het context pack dat bedoeld is voor architectuur- en structuurreview.

## Pack doel

Het context pack is een **briefing pack** (geen bewijs pack) voor:

- canonical systeemstructuur
- module-identiteit en boundaries
- actieve werkpaden in de suite

## Pack refresh

- **Laatste sync (inhoud):** 2026-04-25 — module-README’s en canonical docs opnieuw gekopieerd vanuit de live repos onder `quantmetrics-suite`.
- **Gekoppelde run-id (audit):** `qb_run_20260425T042136Z_dbd1b0cc` (`EXP-2025-baseline` / `single`).

## Actuele context pack (zip + uitgepakte map)

Alle mentor-packs staan onder `docs/` (zodat ze in de repo mee te versionen zijn):

- **Zip:** `C:\Users\Gebruiker\quantmetrics-suite\docs\v1_1_context_pack_qb_run_20260425T042136Z_dbd1b0cc.zip`
- **Map:** `C:\Users\Gebruiker\quantmetrics-suite\docs\v1_1_context_pack_qb_run_20260425T042136Z_dbd1b0cc\`

## Inhoud van de context pack

### `01_CANONICAL_STRUCTURE/`

- `suite_root_README.md` (kopie van `docs/README.md`)
- `SYSTEM_CANONICAL_STRUCTURE.md` (kopie van `docs/SYSTEM_CANONICAL_STRUCTURE.md`)

### `02_MODULE_IDENTITY/`

- `quantbuild_README.md`
- `quantbridge_README.md`
- `quantlog_README.md`
- `quantanalytics_README.md`
- `quantmetrics_os_README.md`
- `quantresearch_README.md` (indien aanwezig in de workspace)

### `03_MENTOR_OVERVIEW/`

- `PATH_OVERVIEW_MENTOR.md`

## Gekoppelde audit pack (bewijs op run-niveau)

- **Zip:** `C:\Users\Gebruiker\quantmetrics-suite\docs\v1_1_audit_pack_qb_run_20260425T042136Z_dbd1b0cc.zip`
- **Map:** `C:\Users\Gebruiker\quantmetrics-suite\docs\v1_1_audit_pack_qb_run_20260425T042136Z_dbd1b0cc\`

Bevat o.a. `03_CONFIGS/`, `04_RUNTIME_EXAMPLE/` (inclusief `analytics_bundle/`), `05_DECISION_ENGINE/`.

## Volledig systeembeeld voor de mentor

- `C:\Users\Gebruiker\quantmetrics-suite\docs\SYSTEM_OVERVIEW_FOR_AI_MENTOR.md`

## Gebruik

- Gebruik **context pack** voor architectuur-, naming- en boundary-audit.
- Gebruik **audit pack** voor run-evidence (events/config/analytics/decision-engine snapshots).
- Gebruik **SYSTEM_OVERVIEW_FOR_AI_MENTOR** als eerste lees-document voor de AI mentor vóór diep in module-docs duikt.
