# QuantLog Roadmap Execution Status

Dit document geeft een compleet overzicht van de stappen die nog kwamen en hun huidige status.

**Strategische volgende fase (operations + data discipline, correlatie, eventtypen, nightly rapportage):** zie **[PLATFORM_ROADMAP.md](PLATFORM_ROADMAP.md)**.

## Fase-overzicht

| Fase | Doel | Status |
|---|---|---|
| 1 | CI hardening (tests + smoke + gates) | Done |
| 2 | Contract integration (fixtures + checks) | Done |
| 3 | Sample-day scenario uitbreiding | Done |
| 4 | Run quality scorecard | Done |
| 5 | Ops runbook + mentor reporting | Done |

---

## 1) CI hardening

Opgeleverd:

- `scripts/ci_smoke.ps1`
- `.github/workflows/ci.yml`

Gates in CI:

- unit tests
- contract fixture checks
- end-to-end smoke runner
- sample day generation
- validate/summarize/ingest health
- positive quality pass gate
- negative anomaly quality fail gate

Status: **Done**

---

## 2) Contract integration

Opgeleverd:

- `tests/fixtures/contracts/quantbuild_dry_run.jsonl`
- `tests/fixtures/contracts/quantbridge_dry_run.jsonl`
- `scripts/contract_check.py`
- `tests/test_contracts.py`

Doel:

- schema drift vroeg detecteren
- broncontracten toetsbaar maken buiten losse unit tests

Status: **Done**

---

## 3) Scenario-uitbreiding synthetic day

Opgeleverd in `scripts/generate_sample_day.py`:

- happy
- blocked
- rejected
- partial_fill
- governance_pause
- failsafe_pause
- adaptive_mode
- session restart probe (`--include-session-restart-probe`)
- anomaly injection (`--inject-anomalies`)

Status: **Done**

---

## 4) Run quality scorecard

Opgeleverd:

- `src/quantlog/quality/service.py`
- CLI command `score-run`

Scorefactoren:

- validation errors/warnings
- invalid JSON
- audit gaps
- duplicate event IDs
- out-of-order events
- missing trace IDs
- missing order refs on execution events

Status: **Done**

---

## 5) Ops en architectuurdocumentatie

Opgeleverd:

- `REPLAY_RUNBOOK.md`
- `MENTOR_UPDATE.md`
- README updates voor contract/quality/scenario flows

Status: **Done**

---

## Huidig besluitpunt

Alle geplande stabilisatiestappen uit de huidige roadmap zijn afgerond.

Volgende logische fase:

1. echte QuantBuild/QuantBridge runtime logs periodiek als contract fixtures updaten
2. quality-score trends opslaan per run (historische scoreline)
3. merge gate aanscherpen op minimale score + max warnings policy

