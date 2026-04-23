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
- [x] Interne `trade_action` / guard-redenen → QuantLog-canonical (`quantlog_no_action.py`, duplicate key verwijderd); AST-test op literal NO_ACTION-redenen + `scripts/check_quantlog_linkage.py`
- [x] Geen silent exits op `_check_signals` / `_check_signals_research_raw_first` / `_evaluate_and_execute`: elke exit emitteert terminal `trade_action`; execution failure emitteert nu ook `risk_guard_decision`
- [x] `signal_detected`: gestructureerde payload (`type`, `direction`, `session`, `regime`, …) — geen vrije-tekst “reason”; detail volgens `QUANTBUILD_EVENT_PRODUCER_SPEC.md`

**Repo:** `quantbuildv1`

---

## Fase 2 — QuantBridge (execution correctness)

- [x] `order_filled` payload: `requested_price`, `fill_price`, `slippage`, `fill_latency_ms`, `spread_at_fill` (uit `place_and_validate` + quote vóór/na fill), `trade_id` + `order_ref` op JSONL-envelope/payload
- [x] `order_submitted` / `order_filled` QuantLog-payload: `trade_id` verplicht; `decision_cycle_id` meesturen wanneer bekend in `TradeRequest` (orchestrator + check-script)
- [x] `order_submitted` na geaccepteerde place (niet bij `risk_blocked`); `order_filled` na bevestigde fill
- [x] `trade_executed` na `order_filled` (QuantBridge orchestrator → JSONL-sink; direction LONG|SHORT)
- [ ] `trade_closed` vanuit broker-sync / positie-close — nog te koppelen; payload-doelset: `exit_reason`, `entry_time_utc`, `exit_time_utc`, `holding_time_seconds`, `net_pnl`, `r_multiple`, `mae`, `mfe` (+ QuantLog-schema uitbreiden waar nodig)

**Repo:** `quantbridgev1`

---

## Fase 3 — QuantLog (validatie)

- [x] Schema-validatie (keten-MVP): verplichte `decision_cycle_id` op QuantBuild keten-events + `trade_id` bij `trade_action` ENTER; enums overig nog uitbreiden waar nodig
- [x] Sequence-validatie (keten-deel): per `decision_cycle_id` exact één `trade_action`, monotone ketenorde (`signal_detected` → `signal_evaluated` → `risk_guard_decision` → `trade_action`); trade lifecycle nog apart
- [x] Referential checks (deel): cross-event stabiliteit voor `trade_id` + `order_ref` (run/session/trace + symbol; envelope vs payload gelijk); keten-keys op `decision_cycle_id`: zelfde `run_id` / `session_id` / `trace_id`; `symbol` fout bij conflict, **warn** bij gedeeltelijk ontbreken
- [x] Minimaal één volledige run / handelsdag draaien + validatierapport (deel): `scripts/smoke_end_to_end.py` + `scripts/day_validation_report.py`; contract-map `decision_cycle_id`↔`trade_id` op `order_*`

**Repo:** `quantlogv1`

---

## Fase 4 — QuantAnalytics (MVP)

- [x] JSONL → tabellen: **decisions** / **guard_decisions** / **executions** / **closed_trades** (CLI `--export-*-tsv`)
- [x] Metrics (MVP): throughput-funnel + NO_ACTION-verdeling op **eventbasis**; expectancy-stub in `--run-summary-json`
- [x] Output: `run_summary.json` (+ optioneel `--run-summary-md`), rapport onder `output_rapport/`
- [ ] Research-grade rapportage volgens **`docs/ANALYTICS_OUTPUT_GAPS.md`** (o.a. data-quality-blok, funnel per `decision_cycle_id`, guard diagnostics, expectancy slices, exit efficiency — P0/P1 daar)

**Repo:** `quantanalyticsv1`

---

## Fase 5 — Strategy improvement loop

- [ ] Bottleneck-analyse op basis van fase 4 (dominante NO_ACTION, guard-overblocking, execution leak, exits)
- [ ] Gecontroleerde wijzigingen (één hefboom per run) + cross-run vergelijking

**Repo’s:** vooral `quantbuildv1` / configs; metingen uit `quantanalyticsv1`

---

## Meta / repo-hygiëne

- [x] `quantmetrics_os`: `QUANTBUILD_EVENT_PRODUCER_SPEC.md` — echte producerspec (was foutieve kopie van implementation sequence)
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
| 2026-04 | QuantLog: §2.3 linkage ENTER→`trade_id` vs latere events; verplicht `trade_id` op `order_submitted`/`order_filled`; `day_validation_report.py`; QuantBridge envelope `decision_cycle_id` (`quantlogv1` + `quantbridgev1`) |
| 2026-04 | QuantBridge: orchestrator stuurt `trade_id` + optioneel `decision_cycle_id` op order-events; `TradeRequest` uitgebreid (`quantbridgev1`) |
| 2026-04 | QuantAnalytics: MVP `decisions` TSV-export (`quantmetrics_analytics.datasets.decisions`, CLI flag) (`quantanalyticsv1`) |
| 2026-04 | QuantAnalytics: guard/executions/closed_trades TSV + `run_summary.json`/`--run-summary-md`; funnel/NO_ACTION metrics in summary (`quantanalyticsv1`) |
| 2026-04 | QuantBridge: `trade_executed` na fill (LONG/SHORT); QuantLog `source_system` uitbreiding `execution` voor script JSONL (`quantbridgev1` / `quantlogv1`) |
| 2026-04 | `quantmetrics_os`: `QUANTBUILD_EVENT_PRODUCER_SPEC.md` inhoud herschreven (geen kopie meer van implementation sequence) |
| 2026-04 | QuantBuild Fase 1: NO_ACTION-mapping opgeschoond; `risk_guard_decision` bij QuantBridge exec-fouten; AST-contracttest `tests/test_live_runner_trade_action_reasons.py` (`quantbuildv1`) |
