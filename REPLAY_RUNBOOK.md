# QuantLog Replay Runbook

Praktische handleiding voor replay, incident-analyse en dagelijkse observability checks.

---

## 1. Doel

Met deze runbook kun je:

- een specifieke trace end-to-end reconstrueren
- valideren of events schema-compliant zijn
- dagelijkse metrics snel controleren
- ingest gaps en auditproblemen detecteren

Kernprincipe:

> Eerst eventkwaliteit controleren, daarna pas conclusies trekken over strategie/executie.

---

## 2. Basiscommando's

### 2.1 Validate events

```powershell
python -m quantlog.cli validate-events --path data/events/generated/2026-03-29
```

Verwachting:

- `errors_total = 0`
- `warnings_total` zo laag mogelijk

### 2.2 Replay trace

```powershell
python -m quantlog.cli replay-trace --path data/events/generated/2026-03-29 --trace-id <TRACE_ID>
```

Verwachting (happy path):

1. `signal_evaluated`
2. `risk_guard_decision` (`ALLOW`)
3. `trade_action` (`ENTER`)
4. `order_submitted`
5. `order_filled`

### 2.3 Summarize day

```powershell
python -m quantlog.cli summarize-day --path data/events/generated/2026-03-29
```

Verwachting:

- `events_total` > 0
- `trades_attempted` logisch t.o.v. `order_submitted`
- `trades_filled` logisch t.o.v. `order_filled`
- `blocks_total` matcht `risk_guard_decision(BLOCK)`

### 2.4 Ingest health

```powershell
python -m quantlog.cli check-ingest-health --path data/events/generated/2026-03-29 --max-gap-seconds 120
```

Bij gaps:

```powershell
python -m quantlog.cli check-ingest-health --path data/events/generated/2026-03-29 --max-gap-seconds 120 --emit-audit-gap
```

---

## 3. Snelle dagelijkse routine (5 minuten)

1. `validate-events` draaien.
2. `summarize-day` draaien.
3. Minimaal 1 random happy-trace replayen.
4. Minimaal 1 blocked-trace replayen (`trade_action = NO_ACTION`).
5. `check-ingest-health` draaien.

Als stap 1 of 5 faalt, geen inhoudelijke performance-analyse doen voordat logging-gaten zijn opgelost.

---

## 4. Incident-workflows

## 4.1 "Waarom is er geen trade genomen?"

Checklist:

1. Replay de trace.
2. Check `risk_guard_decision`.
3. Check `trade_action` decision.

Interpretatie:

- `BLOCK` + `NO_ACTION` -> expected non-trade.
- `ALLOW` + `NO_ACTION` -> strategie/decision-layer issue.

## 4.2 "Waarom mismatch tussen entry intent en execution?"

Checklist:

1. `trade_action` moet `ENTER` zijn.
2. Zoek `order_submitted`.
3. Zoek `order_filled` of `order_rejected`.

Interpretatie:

- `ENTER` zonder `order_submitted` -> orchestration gap.
- `order_submitted` zonder `order_filled`/`order_rejected` -> lifecycle gap.
- `order_rejected` aanwezig -> execution/broker issue (geen strategy issue).

## 4.3 "Waarom lijkt replay niet in goede volgorde?"

Checklist:

1. Controleer `timestamp_utc`.
2. Controleer `source_seq`.
3. Controleer `ingested_at_utc`.

Sortering hoort te zijn:

1. `timestamp_utc`
2. `source_seq`
3. `ingested_at_utc`

---

## 5. Kwaliteitsgates

## 5.1 Event quality gate

Moet waar zijn:

- `errors_total == 0`
- verplichte envelopevelden overal aanwezig
- enum-validatie op decisions slaagt

## 5.2 Replay integrity gate

Moet waar zijn:

- trace bevat expected lifecycle events
- volgorde is deterministisch
- trace heeft consistente `run_id`, `session_id`, `environment`

## 5.3 Ops gate

Moet waar zijn:

- `gaps_found == 0` of verklaard met emitted `audit_gap_detected`
- summary metrics zijn intern consistent

---

## 6. Veelvoorkomende failure-patronen

1. Legacy payload values (`TRADE` i.p.v. `ENTER`)  
   -> fix emitter mapping op bronzijde.

2. Ontbrekende run-context velden (`run_id`, `session_id`)  
   -> emitter init contract niet correct toegepast.

3. Out-of-order gevoel bij gelijke timestamps  
   -> controleer `source_seq` increment discipline.

4. Hoge block-count zonder duidelijke reason  
   -> guard payload standaardiseren (`guard_name`, `reason` verplicht).

5. Ingest gaps zonder audit-event  
   -> health check met `--emit-audit-gap` in dagelijkse routine opnemen.

---

## 7. Aanbevolen operator flow

Voor elke nieuwe build:

1. `python scripts/smoke_end_to_end.py`
2. `python scripts/generate_sample_day.py ...`
3. `validate-events`
4. `summarize-day`
5. minimaal 2 trace replays

Pas daarna doorgaan naar bredere regressie of live/paper evaluatie.

