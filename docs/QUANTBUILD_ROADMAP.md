# QuantBuild roadmap — operations & observability

**Doel:** backlog **alleen voor deze repo** (`quantbuild_e1_v1`), afgestemd op het gedeelde platform-document in **QuantLog**: `docs/PLATFORM_ROADMAP.md` (correlatie, canonieke reasons, lifecycle, nightly rapportage).  
**Werkwijze:** van boven naar beneden; in PR’s verwijzen naar *QuantBuild roadmap §X* of *PLATFORM_ROADMAP §6 P1*.

---

## 1) Waar QuantBuild nu staat

| Onderdeel | Status (kort) |
|-----------|----------------|
| QuantLog JSONL emitter | Aan via config (`quantlog.enabled`); schrijft naar `data/quantlog_events/<UTC-datum>/quantbuild.jsonl` |
| `trade_action` | Op alle beslis-exit-paden in `_check_signals` / `_evaluate_and_execute`; reasons via `quantlog_no_action.canonical_no_action_reason` |
| `signal_evaluated` / `risk_guard_decision` | **Pre-signal exits:** `signal_evaluated` met `setup=false`, `signal_direction=NONE`, `eval_stage=<internal>` + `trade_action` deelt **`cycle_trace_id`**. **Met signal:** per richting eigen `trace_id` zoals voorheen. |
| Correlatie | `run_id` / `session_id` nooit leeg (lege YAML + env `QUANTBUILD_RUN_ID` / `INVOCATION_ID`); `source_seq` monotoon in emitter |
| Trace | Eén `cycle_trace_id` per `_check_signals`-ronde voor alle exits vóór entry-signalen; daarna per richting aparte trace |

---

## 2) Prioriteit 1 — Correlatie (infrastructuur)

**Doel:** geen structurele `invalid_run_id` / `invalid_session_id` in QuantLog-validatie; één stabiele run per proces; session-id begrijpelijk voor operators.

| # | Taak | Repo |
|---|------|------|
| P1.1 | **`run_id` nooit leeg:** als config `run_id` ontbreekt of lege string is → altijd fallback (bv. timestamp- of env-gebaseerde id). Zelfde id voor de hele `LiveRunner`-levensduur. | `live_runner.py` |
| P1.2 | **`session_id` nooit leeg:** zelfde logica als P1.1 voor lege string; documenteer in dit bestand wat “sessie” betekent (nu: typisch één id per processtart). | idem |
| P1.3 | **Optioneel:** `run_id` uit omgeving overnemen (`QUANTBUILD_RUN_ID`, systemd `INVOCATION_ID`). | `live_runner.py` |
| P1.4 | **Controle:** `validate-events` op echte dagmap | Zie `OPERATOR_CHEATSHEET.md` §10 |

---

## 3) Prioriteit 2 — Canonieke `NO_ACTION` & volledige dekking

**Doel:** elke cycle die nu “stil” eindigt, moet waar nodig **analyseerbaar** zijn (histogram per reason in QuantLog `summarize-day`).

| # | Taak | Repo |
|---|------|------|
| P2.1 | **Audit alle return-paden** in `_check_signals` / `_evaluate_and_execute` | ✅ afgehandeld + regressietests op mapping |
| P2.2 | **`quantlog_no_action.py`:** `LIVE_RUNNER_NO_ACTION_INTERNAL_CODES` + tests dat elke internal → QuantLog-canoniek | ✅ |
| P2.3 | **Config/docs:** productie-YAML mag geen lege `quantlog.run_id` / `session_id` tenzij bewust (liever weglaten voor default). | `configs/*.yaml` (optioneel comment) |
| P2.4 | **Telegram vs QuantLog:** hourly counters blijven operationeel; QuantLog blijft bron voor aggregatie | — |

---

## 4) Prioriteit 3 — Lifecycle-events (richting volledige keten)

**Doel:** waar het platform-document een keten beschrijft (`signal_evaluated` → `risk_guard_decision` → `trade_action` → …), QuantBuild daar **consistent** op leveren.

| # | Taak | Repo |
|---|------|------|
| P3.1 | **Early exits vóór SQE-signalen:** `signal_evaluated` + `trade_action`, één `cycle_trace_id` | ✅ |
| P3.2 | **Zelfde `trace_id` per besliscyclus** voor pre-signal pad | ✅ |
| P3.3 | **Bridge-events:** orders/fills blijven primair QuantBridge | architectuur |

---

## 5) Prioriteit 4 — Rapportage & VPS (lichtgewicht)

**Doel:** vaste validatie van eventdagen zonder handmatige zoektocht.

| # | Taak | Repo |
|---|------|------|
| P4.1 | **Documenteren:** QuantLog clone op VPS | ✅ `OPERATOR_CHEATSHEET.md` |
| P4.2 | **Optioneel:** systemd timer + install script | ✅ `deploy/systemd/quantbuild-quantlog-report.{service,timer}`, `scripts/vps/quantlog_nightly.sh`, `install_quantlog_nightly_timer.sh` |
| P4.3 | **Default `--quantlog-repo-path`:** VPS `/opt/quantbuild/quantlog-v.1`, env `QUANTLOG_REPO_PATH`, anders sibling `quantLog v.1` | ✅ `scripts/quantlog_post_run.py` |

---

## 6) Niet in scope (bewust)

- PnL-optimalisatie of strategie-parameters (pas **na** betrouwbare “waarom geen trade”-meting).
- Vervangen van QuantLog door alleen Telegram.
- Volledig dashboard in deze repo (platform-fase; zie QuantLog roadmap).

---

## 7) Voortgang (compact)

| Blok | Status |
|------|--------|
| P1 Correlatie | ✅ code · checklist §10 operator cheatsheet |
| P2 NO_ACTION-dekking & mapping | ✅ |
| P3 Lifecycle-consistentie (pre-signal) | ✅ |
| P4 Rapportage / VPS-docs | ✅ (timer + cheatsheet + runbook) |

**CI:** `.github/workflows/ci.yml` draait `pytest` en `scripts/check_quantlog_linkage.py` (zonder QuantLog-clone: **WARNING**, exit 0). Lokaal/VPS met clone: volledige CLI-validatie + NO_ACTION-set check.

---

## 8) Gerelateerde documenten

| Document | Rol |
|----------|-----|
| QuantLog `docs/PLATFORM_ROADMAP.md` | Gedeelde volgorde Build / Bridge / Log |
| `docs/VPS_MULTI_MODULE_DEPLOYMENT.md` | Paden, venv, QuantLog clone + nightly timer (§5.3) |
| `docs/OPERATOR_CHEATSHEET.md` | Dagelijkse commands + eerste-keer QuantLog clone |
| `.github/workflows/ci.yml` | GitHub Actions: pytest |
| `tests/fixtures/quantlog/minimal_day/quantbuild.jsonl` | Vast contract voor emitter-vorm |
| `scripts/check_quantlog_linkage.py` | Koppelcheck: fixture + schema alignment; zie `OPERATOR_CHEATSHEET.md` §11 |
| `src/quantbuild/quantlog_repo.py` | Pad-resolutie QuantLog-repo (`QUANTLOG_REPO_PATH`, VPS, sibling) |
| `scripts/quantlog_post_run.py` | validate + summarize + score + replay (één dag) |
| `src/quantbuild/execution/quantlog_no_action.py` | Canonieke NO_ACTION mapping |
