# Platform roadmap — operations, data & correlatie

**Doel:** één backlog voor de overgang naar **operations + data discipline**: niet alleen bouwen, maar **aantonen wat het systeem doet** (Telegram = nu, QuantLog = waarheid/audit/analyse).

**Scope:** stappen zitten deels in **QuantBuild** (emitter, strategie), **QuantBridge** (execution-events), **QuantLog** (validatie, CLI, CI). Dit document is de **gezamenlijke** volgorde; technische waarheid voor paden blijft per repo (`VPS_SYNC.md`, QuantBuild-docs).

**QuantBuild & QuantBridge expliciet meenemen:** deze roadmap hoort **niet** alleen in het QuantLog-repo gelezen te worden. De openstaande onderdelen — vooral **P1** (correlatie in de emitter), **P2** (canonieke `NO_ACTION`-reasons in de bot), **P3** (lifecycle-events emitten), execution-consistentie in **Bridge** — moeten **in de respectievelijke repo’s** worden opgepakt (issues/PR’s). Gebruik dit MD als **gedeelde backlog-referentie** (bijv. in een PR: *PLATFORM_ROADMAP §6 P1*), zonder dat hier alle implementatiedetails van Build/Bridge worden gedupliceerd.

**Werkwijze:** werk de blokken **van boven naar beneden** af; vink onderaan af wat klaar is — **per component** (Build / Bridge / Log / VPS) waar van toepassing.

---

## 1) Waar we nu staan

| Fase | Betekenis |
|------|-----------|
| Voorbij | Alleen feature bouwen zonder meetbare geschiedenis |
| **Nu** | **Operations + data discipline**: events, validatie, replay, score, wekelijkse analyse |
| Straks | Geautomatiseerde kwaliteitsrapportage + uitgebreidere lifecycle-events |

---

## 2) Lagen in de stack (wie beantwoordt welke vraag)

| Laag | Vraag |
|------|--------|
| **Trading bot (QuantBuild)** | Waarom trade je (of niet)? |
| **Telegram** | Wat doe de bot *nu* (operator / monitoring)? |
| **QuantLog** | Wat is er *echt* gebeurd en waarom (audit / research)? |

Aansluiting execution:

| Component | Rol |
|-----------|-----|
| **QuantBuild** | Beslissingen, guards, `trade_action` |
| **QuantBridge** | Orders, fills, execution (waar al events vandaan komen) |

---

## 3) Twee observatielagen (bewust gescheiden)

1. **Telegram → operationeel dashboard**  
   NO_ACTION / ENTER, regime, balans, laatste uur — *geen* vervanging van audit trail.

2. **QuantLog → waarheid / audit / analyse**  
   Alle events, correlatie, replay, validatie, score, historische analyse.

Die scheiding is gewenst: **operator** vs **truth layer**.

---

## 4) Belangrijk inzicht uit de data (geen “logging bug”)

Symptoom: grote stroom `trade_action` met `NO_ACTION` / `cooldown_active`, **`trades_attempted: 0`**.

**Interpretatie:** de bot draait, evalueert, regime en guards en cooldown werken — maar er worden **geen trades geprobeerd**. Dat is een **strategie- / filter- / throughput-vraag**, geen QuantLog-ingest-fout.

**Gevolg:** `NO_ACTION`-**reasons** moeten betrouwbaar en **uit te aggregeren** zijn (histogram per reason), anders kun je niet sturen op optimalisatie.

---

## 5) Technische blocker: lege correlatievelden

Als validatie **`invalid_run_id` / `invalid_session_id`** geeft, is dat **P1-infrastructuur**, geen cosmetiek.

Zonder consistente correlatie mis je o.a.:

- run-vergelijkingen en run-scores
- sessie-analyse
- betrouwbare replay
- audit trail die over events heen klopt

### Correlatie-contract (doeltoestand)

Elk event moet (waar van toepassing) minimaal hebben:

| Veld | Eis |
|------|-----|
| `run_id` | Nooit leeg; **zelfde** id voor de hele run |
| `session_id` | Nooit leeg; **per sessieblok** consistent |
| `trace_id` | Waar relevant voor één beslissingsketen |
| `source_seq` | Monotoon **per producer** |
| `timestamp_utc` | Correct en vergelijkbaar |

**Volgorde:** eerst **emitter-fix in QuantBuild** (en waar nodig Bridge) → daarna heeft **CI / `validate-events`** pas zin als harde poort.

---

## 6) Prioriteit 1 — Correlatie fix (infrastructuur)

**Repo-focus:** vooral **QuantBuild** (emitter / context die mee gaat bij elke logregel).

**QuantLog (deze repo) — gestart:**

- [x] Validatie: JSON `null` / lege string voor `run_id` / `session_id` / `trace_id` → `invalid_*` (niet meer sluipend geldig)
- [x] Validatie: `source_seq` strikt oplopend per stroom binnen één JSONL-bestand (`source_seq_not_monotonic`)

**Nog in QuantBuild / productie-emitter:**

- [ ] `run_id` nooit leeg; één stabiele `run_id` per procesrun
- [ ] `session_id` nooit leeg; duidelijke definitie “sessieblok” en hergebruik binnen dat blok
- [ ] `trace_id` daar waar een keten (signal → guard → action) traceerbaar moet zijn
- [ ] `source_seq` monotoon per producer (emitter); QuantLog controleert per bestand
- [ ] `timestamp_utc` conform contract (zie `EVENT_SCHEMA.md`)
- [ ] Her-run `validate-events` op echte dagen: geen `invalid_run_id` / `invalid_session_id` meer structureel

---

## 7) Prioriteit 2 — `NO_ACTION` reasons compleet en canoniek

**Doel:** elke cycle eindigt waar nodig met een duidelijke `trade_action` met `decision: NO_ACTION` en **`reason`** die je later kunt tellen.

**QuantLog (deze repo) — gedaan / ondersteunend:**

- [x] Canonieke reason-set in code: `NO_ACTION_REASONS_CORE` / `NO_ACTION_REASONS_EXTENDED` in `events/schema.py`; `validate-events` weigert niet-canonieke reasons bij `NO_ACTION`
- [x] `summarize-day`: velden `no_action_by_reason` en `trade_action_by_decision` in de JSON-output (histogram)

**Nog in QuantBuild (emitter / strategie):**

### Canonieke reasons (uitgangspunt)

Gebruik **exact deze strings** (uitbreiden alleen bewust en gedocumenteerd):

- [ ] `no_setup`
- [ ] `regime_blocked`
- [ ] `session_blocked`
- [ ] `risk_blocked`
- [ ] `spread_too_high`
- [ ] `news_filter_active`
- [ ] `cooldown_active`

**Analyse-doel:** histogram zoals “reason × count” om throughput te sturen.

---

## 8) Prioriteit 3 — Eventtypen uitbreiden (lifecycle-richting)

**Beleid:** QuantLog moet uiteindelijk de **volledige** keten kunnen volgen: beslissing → guard → execution → positie. Niet alles tegelijk bouwen; wél **richting vastleggen**.

### Minimaal kortetermijn (na P1–P2)

- [x] **QuantLog:** `signal_evaluated` en `risk_guard_decision` in schema + validator (`EVENT_PAYLOAD_REQUIRED`)
- [ ] **Productie:** beide eventtypen daadwerkelijk emitten waar de lifecycle dat vereist

### Volledige lifecycle (doelbeeld; execution deels al Bridge)

| Event | Opmerking |
|-------|-----------|
| `signal_evaluated` | Setup / geen setup |
| `risk_guard_decision` | Blok / allow + reden |
| `trade_action` | ENTER / NO_ACTION |
| `order_submitted` | Bridge |
| `order_filled` | Bridge |
| `position_opened` | Bridge / Build (afspraak per stack) |
| `position_closed` | idem |
| `stop_moved` / `tp_hit` | idem |
| `failsafe_triggered` | later |
| `governance_pause` | later |

**QuantLog-repo:** schema’s, validators en fixtures uitbreiden wanneer Build/Bridge nieuwe `event_type`s emitten.

---

## 9) Prioriteit 4 — Dagelijkse validatie automatiseren

**Doel:** naast “wat de bot nu doet” (Telegram) een vaste **datakwaliteit- en runkwaliteit-rapportage**.

Voorstel **nightly** (VPS cron of CI op geïmporteerde dag):

- [x] **QuantLog:** scripts `nightly_quantlog_report.ps1` (Windows) en `nightly_quantlog_report.sh` (Linux/VPS) — zelfde vier CLI-stappen; exitcode = “ergste” fout
- [x] **QuantLog:** CLI `list-no-action-reasons` — JSON met canonieke `NO_ACTION`-reasons voor emitter-alignment
- [x] **QuantLog:** `validate-events` JSON bevat `errors_by_code` / `warnings_by_code`; `score-run` JSON bevat throughput-histogrammen (zelfde als `summarize-day`) naast de score
- [ ] Zelfde keten op VPS (cron / systemd timer) of in CI op geïmporteerde dagmap
- [ ] Optioneel: push naar **Telegram / Slack / mail** (één kanaal is genoeg om te starten)

---

## 10) Data-overdracht productie → analyse

**Nu:** handmatige flow VPS → archief → laptop is **bewust voldoende** tot correlatie en eventkwaliteit op orde zijn.

Details en latere opties (rsync, S3, artifacts, ingest, Parquet, warehouse): **[DATA_TRANSFER_ROADMAP.md](DATA_TRANSFER_ROADMAP.md)** en stap-voor-stap **[WEEKLY_ANALYSIS_WORKFLOW.md](WEEKLY_ANALYSIS_WORKFLOW.md)**.

---

## 11) Samenvatting (één zin per onderdeel)

- **Telegram** = wat de bot nu doet  
- **QuantLog** = wat er echt gebeurd is en waarom  
- **JSONL** = beslissings- en systeemgeschiedenis  
- **`validate-events`** = klopt die geschiedenis structureel?  
- **Replay** = klopt het verhaal end-to-end?  
- **Summarize** = wat gebeurde er die dag?  
- **`score-run`** = was dit een schone / bruikbare run?  

---

## 12) Voortgang (compact)

| Blok | Status |
|------|--------|
| P1 Correlatie | ☐ niet gestart · ☐ bezig · ☐ af |
| P2 NO_ACTION reasons | QuantLog kant: histogram + validatie · Build: reasons in productie |
| P3 Nieuwe eventtypen (fase 1) | Schema OK · productie-emit nog plannen |
| P4 Nightly rapportage | Script lokaal · VPS/CI + notificatie nog open |
| Data-overdracht (huidige flow stabiel) | ☐ niet gestart · ☐ bezig · ☐ af |

*Vervang ☐ door ✅ in je kopie of werk met issues/PR’s per checkbox.*

---

## Gerelateerde documenten

| Document | Rol |
|----------|-----|
| [EVENT_SCHEMA.md](EVENT_SCHEMA.md) | Envelope en payload-contracten |
| [ROADMAP_EXECUTION_STATUS.md](ROADMAP_EXECUTION_STATUS.md) | Afgeronde QuantLog-MVP-fasen (CI, scorecard, …) |
| [DATA_TRANSFER_ROADMAP.md](DATA_TRANSFER_ROADMAP.md) | Sync nu vs. later |
| [WEEKLY_ANALYSIS_WORKFLOW.md](WEEKLY_ANALYSIS_WORKFLOW.md) | Praktische weekanalyse op laptop |
| [VPS_SYNC.md](VPS_SYNC.md) | VPS-pull en waar QuantLog staat |
