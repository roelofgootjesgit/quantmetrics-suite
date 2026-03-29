# Quant stack integration acceptance — truth-loop dossier

Dit document legt **stack-integratie-acceptances** vast: QuantBuild + QuantBridge + QuantLog (`run → log → validate → replay → summarize → quality`).

Historisch onderscheid:

| ID | Type | Wat het bewijst |
|----|------|-----------------|
| **001** | **Hybrid fixture-assisted integration acceptance** | Canonieke emits, correlatie, QuantLog-pipeline op echte integratie-output — met **bewuste** fixture-aanvulling waar de live-loop geen events produceerde. |
| **002** | **Pure live-loop session acceptance** | QuantBuild-events **uitsluitend** uit de live signal-loop, in een entry-capable venster — **zonder** handmatige emitter-aanvulling. |

---

## Referentie-integratie (repo commits — stack-wiring)

| Repo | Branch | Commit (volledig) | Onderwerp |
|------|--------|-------------------|-----------|
| quantbuildE1 | `v2-development` | `3cf42b81549223a9fa2804f6c1a4e6c414cbab63` | Integrate QuantLog emitter into live runner and add post-run pipeline |
| quantBridge-v.1 | `main` | `ccdea09a4e83ef1c401b14aae18d20c2ecec7cc9` | Make observability sink QuantLog-compatible with canonical envelope |
| quantLog v.1 | `main` | `c4f12fd10853ac64aa5cbb83067c87b1201df0cd` | Acceptance 001 resultaten ingevuld + QuantLog CLI |

*(Latere commits op `main` kunnen dit dossier alleen documentair bijwerken; integratietests refereren aan de SHAs hierboven.)*

---

# Acceptance 001 — Hybrid fixture-assisted integration acceptance

**Acceptance ID:** `INTEGRATION_ACCEPTANCE_001`  
**Acceptance type:** Hybrid fixture-assisted integration acceptance  
**Status:** **PASS with caveat** — integratie-acceptance **geslaagd**; **autonome live-loop acceptance** (zie 002) nog open.

**Caveat (historisch zuiver):** QuantBuild-events in dit dossier kwamen **niet** puur uit `_check_signals` in de getimede run-window; ze zijn **aangevuld** via dezelfde productie-modules (`QuantLogEmitter`, `JsonlEventSink`). Dat rechtvaardigt **geen** interpretatie als “volledig coherent lifecycle” zonder de fixture-caveat hieronder.

---

## Run config (001)

- **Datum (UTC):** `2026-03-29`
- **QuantBuild config:** `configs/strict_prod_v2.yaml`
- **`quantlog.enabled`:** `true`
- **`quantlog.base_path`:** `data/quantlog_events` (relatief t.o.v. QuantBuild repo-root)
- **`quantlog.environment`:** `dry_run`
- **QuantBridge:** ja — `JsonlEventSink` naar `data/quantlog_events/2026-03-29/quantbridge.jsonl` (zelfde dagmap als QuantBuild)
- **Host:** Windows 10; Python 3.11

---

## Uitgevoerde stappen (001)

1. **QuantBuild live dry-run** — `python -m src.quantbuild.app --config configs/strict_prod_v2.yaml live` met proces-timeout **90 s** (`PYTHONPATH` = QuantBuild repo-root).  
   - Bootstrap **OK** (XAUUSD 15m/1h via Dukascopy), QuantLog-emitter **actief**, regime-update uitgevoerd.  
   - Om **19:35 UTC** viel de sessie buiten `ENTRY_SESSIONS` (**Asia** bij `session_mode: extended`) → **`_check_signals` niet uitgevoerd** → *session-gating in QuantBuild, geen QuantLog-fout*. In deze slice **geen** spontane regels in `quantbuild.jsonl`.

2. **Fixture-aanvulling (zelfde productiecode)** — decision + execution events zodat keten en correlatie aantoonbaar zijn:  
   - **QuantBuild:** `QuantLogEmitter` — `signal_evaluated`, `risk_guard_decision`, `trade_action`.  
   - **QuantBridge:** `JsonlEventSink.emit` — `order_submitted`, `order_filled`, met **dezelfde `trace_id`**.

3. **Post-run pipeline** — QuantLog CLI + `scripts/quantlog_post_run.py`  
   - CLI: `PYTHONPATH=<quantLog>/src`  
   - Post-run script: **`PYTHONPATH=<quantbuild repo-root>`** (anders `ModuleNotFoundError: src.quantbuild`).

---

## Resultaten (001)

### Paden

- **Dagmap:** `quantbuild_e1_v1/data/quantlog_events/2026-03-29/`
- **Bestanden:** `quantbuild.jsonl` (3 events), `quantbridge.jsonl` (2 events)

### Event counts

| Bron | Bestand | Events | Opmerking |
|------|---------|--------|-----------|
| QuantBuild | `quantbuild.jsonl` | 3 | Fixture-assisted + gedeelde trace |
| QuantBridge | `quantbridge.jsonl` | 2 | `order_submitted`, `order_filled` |
| **Totaal** | map | **5** | `summarize-day` / `score-run` |

### Correlatievelden (steekproef)

| Veld | Aanwezig | Voorbeeld |
|------|----------|-----------|
| `trace_id` (Build + Bridge) | ja | `trace_acceptance_5c44c5452d` |
| `order_ref` (execution) | ja | `ord_acc_xau_001` |
| `run_id` / `session_id` | ja | o.a. `acceptance_210625563053`, `acceptance_bridge_001` |

### `validate-events`

- **Status:** **PASS**
- **Samenvatting:** `files_scanned=2`, `lines_scanned=5`, `events_valid=5`, **`errors_total=0`**, `warnings_total=0`

### `summarize-day`

- **Verwachte eventtypen aanwezig:** `signal_evaluated`, `risk_guard_decision`, `trade_action`, `order_submitted`, `order_filled`
- **`by_event_type`:** elk type **1×**
- **`blocks_total`:** 1 · **`trades_filled`:** 1 (afgeleid uit summaries)

### `score-run` (threshold 95)

- **Score:** **100** · **Grade:** A+ · **`passed`:** **true**
- **Penalties:** `duplicate_event_ids=0`, `out_of_order_events=0`, `missing_trace_ids=0`, `missing_order_ref_execution=0`, `audit_gaps=0`

### `replay-trace` (sanity)

- **`trace_id`:** `trace_acceptance_5c44c5452d`
- **`events_found`:** **5**
- **Status:** **coherent** voor fixture-doeleinden — tijdlijn: Build (signal → guard → NO_ACTION) gevolgd door Bridge (submit → fill)

---

## Minimum criteria (001)

| Criterium | Uitslag |
|-----------|---------|
| validate: 0 errors | ja |
| replay: eerste trace coherent | ja (binnen fixture) |
| summary: verwachte eventtypes | ja |
| score-run: boven threshold | ja (100 ≥ 95) |
| correlatie: trace_id / order_ref / run_id | ja |
| geen onverwachte duplicate / audit-gap | ja |

---

## Bekende afwijkingen / issues (001)

1. **Geen puur autonome live-loop:** zie **Acceptance 002** voor de ontbrekende architectuurstap.

2. **Bridge vs Build narrative (fixture):** `order_filled` op dezelfde trace als `trade_action: NO_ACTION` is **bewust** inconsistent als “één werkelijke lifecycle”; bij **echte** runs moet het verhaal kloppen. Gebruik deze data niet ongemerkt als ground truth voor lifecycle-coherentie.

3. **`quantlog_post_run.py`:** vereist `PYTHONPATH` naar QuantBuild root.

4. **`source_seq`:** per bron opnieuw vanaf 1 — verwacht gedrag.

5. **Trace-discipline:** blijf `trace_id` / `order_ref` / `position_id` end-to-end monitoren bij echte Build→Bridge runs.

### Security (infra-schuld)

Bij de live dry-run slice kunnen **secrets** (bijv. Telegram bot token) in **httpx / debug logs** verschijnen. Maatregelen: token **roteren** indien echt, logging **scrubben/redacteren**, voorkomen dat tokens in standaard logregels landen.

---

## Go / no-go (001)

- [x] Validator zonder errors op de acceptance-dag.
- [x] Minstens één trace succesvol gereplayed als sanity check.
- [x] Score-run gedraaid; uitslag genoteerd.
- [x] Afwijkingen expliciet genoteerd.

**Besluit 001:** **GO** voor *integratie-acceptance* en fase 2 (fixtures uit echte logs, scenario’s, hardening) — **mits** Acceptance 002 gepland blijft als aparte **live-loop autonomous** gate.

---

# Acceptance 002 — Pure live-loop session acceptance

**Acceptance ID:** `INTEGRATION_ACCEPTANCE_002`  
**Acceptance type:** Pure live-loop session acceptance  
**Status:** **pending**

**Doel:** bewijzen dat de **volledige QuantBuild-eventketen** spontaan uit de live loop komt **zonder** handmatige `QuantLogEmitter`-aanvulling.

## Testopzet (QuantBuild — geen QuantLog-wijziging nodig)

- Run in **London / New York / Overlap** (UTC), conform `session_mode` in config — entry-capable venster zodat `_check_signals` draait.
- Voldoende **runtime** (langer dan een enkele poll-cyclus; geen kunstmatige stop vóór minstens één evaluatieronde in entry-sessie).
- **`quantlog.enabled: true`**, zelfde `base_path`-afspraak als productie.
- QuantBridge: execution lifecycle events **mee** naar dezelfde dagmap/structuur — **zonder** losse fixture-scripts tenzij expliciet als *mock broker* gedocumenteerd.

## Acceptatiecriteria (002)

- [ ] **Geen** handmatige emitter-aanvulling voor QuantBuild-events op die run-dag.
- [ ] `validate-events`: **0 errors**
- [ ] `summarize-day`: verwachte eventtypes **voor die run** (minstens wat de loop daadwerkelijk emitteert)
- [ ] `score-run`: **pass** (threshold volgens runbook)
- [ ] `replay-trace`: **coherent verhaal per trace** (Build + Bridge consistent — geen NO_ACTION + fill op dezelfde trace tenzij business-logica dat echt toelaat)

## Na invulling

Kopieer voor 002 dezelfde subsecties als bij 001 (run config, stappen, resultaten, caveats) en zet **Status** op PASS / PASS with caveat / FAIL met rationale.
