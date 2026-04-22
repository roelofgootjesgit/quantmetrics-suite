# P0 fix sprints

## Doel

Dit document vertaalt het P0 fix plan naar concrete, uitvoerbare sprints.

Focus:

→ **niet** strategie verbeteren  
→ **niet** nieuwe productfeatures bouwen  

Maar:

→ **data correctness, decision chain en lifecycle volledig herstellen**

Elke sprint heeft scope, taken, acceptance criteria en exit rules.

---

## Overzicht

| Sprint | Focus |
|--------|--------|
| SPRINT 1 | `signal_evaluated` context fix |
| SPRINT 2 | `decision_cycle_id` propagation |
| SPRINT 3 | funnel (detect → evaluate) fix |
| SPRINT 4 | trade lifecycle fix |
| SPRINT 5 | small validation run |
| SPRINT 6 | full rerun + P0 acceptance |

---

## Voortgang (implementatie QuantBuild / bridge)

| Sprint | Status | Notes |
|--------|--------|--------|
| S1 | **Done** | `build_signal_evaluated_payload` + `assert_signal_evaluated_payload_complete`; `live_runner` + `backtest/engine` gebruiken builder; tests in `tests/test_signal_evaluated_payload.py` |
| S2 | **Done** (kern) | `DecisionCycleContext` + `new_decision_cycle_id()`; live poll start bundelt trace+dcid+sessie+regime; backtest `dc_bt_*`; geen ad-hoc `str(uuid4())` meer voor cycle-id; `QuantLogEmitter` fallback; bridge `dc_bridge_*` |
| S3 | **Done** (kern) | Live: synthetische `sqe_pipeline_scan`-detect vóór elke gate-eval; analytics: funnel + `se>sd`-anomaly op QuantBuild-subset; `cycles_signal_evaluated_without_signal_detected` in cycle-funnel |
| S4 | **Done** (kern) | `trade_closed` paden live + backtest; `trade_executed` met cycle id |
| S5 | **Script** | `quantbuildv1/scripts/p0_stack_validate.py` (+ `scripts/p0_sprint5_smoke.py`) |
| S6 | **Manual** | Volledige backtest/dag + QuantAnalytics + checklist `P0_FIX_PLAN.md` |

---

# SPRINT 1 — signal_evaluated context fix

## Doel

Alle `signal_evaluated` events bevatten complete context.

## Probleem

Analytics toont lage `session` / `setup_type` presentie → payload niet consistent.

## Taken

1. Zoek alle emitters (`signal_evaluated`): `live_runner.py`, `backtest/engine.py`.
2. Centraliseer payload build: `build_signal_evaluated_payload` in `execution/signal_evaluated_payload.py`.
3. Verwijder losse hand-built dicts op die paden.
4. Harde invariant: `assert_signal_evaluated_payload_complete` vóór elke emit (live + backtest).

## Acceptance criteria

- `session` / `setup_type` / `regime` / `decision_cycle_id` in payload
- geen lege `<missing>`-achtige context op canonieke paden

## Exit rule

Kleine testrun groen (pytest) → door naar sprint 2 validatie.

---

# SPRINT 2 — decision_cycle_id propagation

## Doel

Eén consistente `decision_cycle_id` per decision chain.

## Taken

1. `DecisionCycleContext` (dataclass) voor bundle-typing.
2. ID vroeg in de cycle; hergebruik op emits (`signal_detected` … `trade_action`).
3. Geen losse `uuid()` per losse emitter zonder cycle-scope (waar consolidated).

## Acceptance criteria

- QuantBuild chain-events: envelope `decision_cycle_id` enforced (`quantlog_emitter`).
- Payload bevat dezelfde id voor downstream analytics.

---

# SPRINT 3 — funnel fix (detect → evaluate)

## Doel

Geen `evaluated > detected` meer door ontbrekende detects.

## Taken

1. Elke evaluatierun begint met `signal_detected` (echt of `sqe_pipeline_scan` gate-anchor).
2. Eén evaluatieve `signal_evaluated` per cycle waar Model A van toepassing is.
3. Tijdelijke logging optioneel via bestaande `decision_cycle` logger.

## Acceptance criteria

- Funnel warnings (`FUNNEL_*`) verdwijnen op nieuwe runs.

---

# SPRINT 4 — trade lifecycle fix

## Doel

Fill → close is sluitend of expliciet open.

## Taken

1. Alle close-paden emit `trade_closed` metzelfde `trade_id` waar mogelijk.
2. `order_submitted` / `order_filled` / `trade_executed` blijven gelinkt (backtest + bridge).

---

# SPRINT 5 — small validation run

## Taken

- `python scripts/p0_sprint5_smoke.py` of `python scripts/p0_stack_validate.py`
- Optioneel: korte backtest-config + analytics warnings check

---

# SPRINT 6 — full rerun + P0 acceptance

## Taken

- Volledige backtest of handelsdag
- QuantAnalytics pipeline
- `KEY_FINDINGS.md` + checklist `P0_FIX_PLAN.md`

---

## Belangrijkste regel

Per sprint: **fix → kleine run → check**. Niet alles tegelijk.

---

## Samenvatting

Eerst correcte data en chain, daarna pas edge-optimalisatie.
