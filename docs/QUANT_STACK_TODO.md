# Quant stack MVP — TODO (levende checklist)

Centrale takenlijst voor de **Quant stack MVP** (QuantBuild → QuantBridge → QuantLog → QuantAnalytics).  
Leidende documenten: `QUANT_STACK_MVP_BLUEPRINT.md`, `QUANT_STACK_IMPLEMENTATION_SEQUENCE.md`, `QUANT_STACK_CANONICAL_IDS_AND_GRAINS.md`, `QUANTANALYTICS_CONSUMER_PLAN.md`, `QUANTBUILD_EVENT_PRODUCER_SPEC.md` (let op: producer-specbestand in repo controleren op juiste inhoud).

**Regel:** geen strategie-tuning vóór logging-compleetheid; geen dashboards vóór genormaliseerde datasets.

---

## Fase 1 — QuantBuild (producer correctness)

- [x] `run_id` / `session_id` consistent op envelope (bestaand pad)
- [x] `decision_cycle_id` op beslisketen-events + backtest volgorde `signal_detected` → `signal_evaluated`
- [x] `trade_action` bij **ENTER**: `trade_id` in payload (live_runner + backtest; CI-contract op ENTER)
- [x] `signal_evaluated`: blueprint-velden waar data bestaat (`setup_type`, `session`/`regime`, `combo_count`, `price_at_signal`, `spread` via live spread + bar close)
- [x] `risk_guard_decision`: canonieke `reason` bij BLOCK + `threshold`/`observed_value`/`session`/`regime` waar meetbaar (o.a. spread-, sizing-, slippage-pad)
- [ ] Interne `trade_action` / guard-redenen 100% naar canonieke enums (QuantLog-schema in sync houden)
- [ ] Geen silent exits: elke evaluatiecyclus eindigt met `trade_action` (ENTER of NO_ACTION) — audit alle vroege `return`-paden
- [ ] `signal_detected` optioneel uitbreiden zonder vrije-tekst-redenen (alleen gestructureerde velden)

**Repo:** `quantbuildv1`

---

## Fase 2 — QuantBridge (execution correctness)

- [x] `order_filled` payload: `requested_price`, `fill_price`, `slippage`, `fill_latency_ms`, `spread_at_fill` (uit `place_and_validate` + quote vóór/na fill), `trade_id` + `order_ref` op JSONL-envelope/payload
- [x] `order_submitted` na geaccepteerde place (niet bij `risk_blocked`); `order_filled` na bevestigde fill
- [ ] `trade_executed` / `trade_closed` in QuantBridge of broker-sync — nog te koppelen aan lifecycle
- [ ] `trade_closed`: `exit_reason`, `entry_time_utc`, `exit_time_utc`, `holding_time_seconds`, `net_pnl`, `r_multiple`, `mae`, `mfe` (veldnamen aligned met canonical doc + QuantLog)

**Repo:** `quantbridgev1`

---

## Fase 3 — QuantLog (validatie)

- [x] Schema-validatie (keten-MVP): verplichte `decision_cycle_id` op QuantBuild keten-events + `trade_id` bij `trade_action` ENTER; enums overig nog uitbreiden waar nodig
- [x] Sequence-validatie (keten-deel): per `decision_cycle_id` exact één `trade_action`, monotone ketenorde (`signal_detected` → `signal_evaluated` → `risk_guard_decision` → `trade_action`); trade lifecycle nog apart
- [x] Referential checks (deel): cross-event stabiliteit voor `trade_id` + `order_ref` (run/session/trace + symbol; envelope vs payload gelijk); keten-keys op `decision_cycle_id`: zelfde `run_id` / `session_id` / `trace_id`; `symbol` fout bij conflict, **warn** bij gedeeltelijk ontbreken
- [ ] Minimaal één volledige run / handelsdag draaien + validatierapport

**Repo:** `quantlogv1`

---

## Fase 4 — QuantAnalytics (MVP)

- [ ] JSONL → tabellen: `decisions`, `guard_decisions`, `executions`, `closed_trades` (of gelijkwaardige grains per consumer-plan)
- [ ] Metrics: throughput-funnel, NO_ACTION-verdeling, expectancy per setup / session / regime
- [ ] Output: `run_summary.json` / `run_summary.md` (of afgesproken artefacten)

**Repo:** `quantanalyticsv1`

---

## Fase 5 — Strategy improvement loop

- [ ] Bottleneck-analyse op basis van fase 4 (dominante NO_ACTION, guard-overblocking, execution leak, exits)
- [ ] Gecontroleerde wijzigingen (één hefboom per run) + cross-run vergelijking

**Repo’s:** vooral `quantbuildv1` / configs; metingen uit `quantanalyticsv1`

---

## Meta / repo-hygiëne

- [ ] `quantmetrics_os`: producer-specbestand inhoud vs. bestandsnaam (`QUANTBUILD_EVENT_PRODUCER_SPEC.md`) rechtzetten indien verkeerde copy
- [ ] Cross-repo: versie-tag of build-id in `run_id` / artefacten voor reproduceerbaarheid (QuantOS-orchestrator wanneer actief)

---

## Voltooide items (archief)

| Datum | Item |
|-------|------|
| 2026-04 | `decision_cycle_id` + tests/fixture; backtest `signal_detected` vóór `signal_evaluated` (`quantbuildv1`) |
| 2026-04 | Guard-telemetry, `signal_evaluated`-blueprint merge, ENTER `trade_id`, `QUANT_STACK_TODO.md` (`quantbuildv1` + `quantmetrics_os`) |
| 2026-04 | QuantBridge: fill-metrics op `OrderLifecycleResult`, canonieke `order_submitted` / `order_filled` via orchestrator + `trade_id` op JSONL (`quantbridgev1`) |
| 2026-04 | QuantLog: validator + emitter voor keten-`decision_cycle_id` en ENTER-`trade_id`; contract-fixture en tests bijgewerkt (`quantlogv1`) |
| 2026-04 | QuantLog: sequence-validatie op decision cycle (terminal `trade_action`, duplicaat-blokkade, ketenorde) (`quantlogv1`) |
| 2026-04 | QuantLog: referentiële correlatie (`trade_id`/`order_ref`) + envelope-payload-afstemming (`quantlogv1`) |
| 2026-04 | QuantLog: decision-chain envelope consistentie per `decision_cycle_id` (run/session/trace/symbol) (`quantlogv1`) |
