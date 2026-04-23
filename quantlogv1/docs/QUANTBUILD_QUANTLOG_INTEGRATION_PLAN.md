# QuantBuild <-> QuantLog Integration Plan

## 1. Doel

Van interne QuantLog-validatie naar echte stack-validatie met live dry-run output:

1. QuantBuild events landen in QuantLog.
2. QuantBridge events landen in QuantLog.
3. Elke run eindigt automatisch in:
   - `validate-events`
   - `replay-trace`
   - `summarize-day`
   - `score-run`

---

## 2. Scope

## In scope

- Event emit integration in QuantBuild (decision layer)
- Event emit integration in QuantBridge (execution layer)
- End-of-run validation pipeline
- Contract checks op echte dry-run logs

## Out of scope

- Nieuwe trading logic
- Dashboard/BI uitbreiding
- ML/data warehouse flows

---

## 3. Integratie-architectuur

```text
QuantBuild (dry-run/live-run)
   -> emit canonical events
QuantBridge (execution lifecycle)
   -> emit canonical events
                 |
                 v
           QuantLog event store
                 |
                 +-> validate-events
                 +-> replay-trace
                 +-> summarize-day
                 +-> score-run
```

---

## 4. Event mapping (minimale set)

## QuantBuild -> QuantLog

- `signal_evaluated`
- `risk_guard_decision`
- `trade_action`
- `adaptive_mode_transition` (wanneer actief)

## QuantBridge -> QuantLog

- `order_submitted`
- `order_filled`
- `order_rejected`
- `governance_state_changed`
- `failsafe_pause` (wanneer relevant)

---

## 5. Integratiestappen

## Stap 1 - QuantBuild emitter wiring

- Voeg QuantLog adapter init toe in QuantBuild run bootstrap.
- Geef verplichte context mee:
  - `environment`
  - `run_id`
  - `session_id`
  - monotone `source_seq`
- Emit events op decision points.

Acceptance:

- dry-run van QuantBuild produceert schema-valide jsonl met `errors_total=0`.

## Stap 2 - QuantBridge emitter wiring

- Voeg QuantLog adapter init toe in QuantBridge runtime.
- Koppel order lifecycle naar `trace_id/order_ref/position_id`.
- Emit governance/failsafe events.

Acceptance:

- QuantBridge dry-run produceert valide jsonl met `errors_total=0`.

## Stap 3 - Correlation discipline

- `trace_id` wordt op decision-niveau gemaakt en downstream hergebruikt.
- `order_ref` komt uit execution en blijft consistent.
- `position_id` wordt gevuld zodra positie bestaat.

Acceptance:

- replay van willekeurige trace geeft complete causal chain.

## Stap 4 - End-of-run pipeline

Na run-afsluiting automatisch:

1. `validate-events`
2. `summarize-day`
3. `check-ingest-health`
4. `score-run`
5. minimaal 1 `replay-trace` sanity check

Acceptance:

- pipeline return code is non-zero bij schema errors of quality fail.

---

## 6. CI/ops gates voor integratiefase

Een geïntegreerde run is alleen "bruikbaar voor research" als:

- `validate-events` errors = 0
- ingest gaps = 0 (of expliciet verklaard)
- replay sanity check geslaagd
- `score-run >= 95`

Bij fail:

- run markeren als non-research-grade
- geen strategieconclusies trekken op die dataset

---

## 7. Risico's en mitigatie

1. Schema drift tussen repos  
   -> contract fixtures periodiek verversen met echte dry-run logs.

2. Correlatiebreuk (`trace_id/order_ref`)  
   -> enforce in integration tests + replay checks.

3. Sequence issues bij meerdere processen  
   -> `source_seq` per emitter + run/session context verplicht.

4. Scope creep in QuantLog  
   -> guardrails blijven merge-voorwaarde.

---

## 8. Deliverables

1. QuantBuild integration patch (emitter wiring)
2. QuantBridge integration patch (emitter wiring)
3. End-of-run runner script (validate/replay/summary/score)
4. Fixture refresh met echte dry-run output
5. Integratie-acceptatieverslag met quality score voorbeelden

---

## 9. Definitie van "integratie geslaagd"

Integratie is geslaagd wanneer:

- beide systemen naar hetzelfde canonieke eventcontract loggen
- een volledige run reproduceerbaar is via replay
- quality gates automatisch afdwingen wat research-grade data is
- regressies vroeg zichtbaar worden via CI

