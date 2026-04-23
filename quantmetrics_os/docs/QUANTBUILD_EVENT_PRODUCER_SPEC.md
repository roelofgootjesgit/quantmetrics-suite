# QUANTBUILD_EVENT_PRODUCER_SPEC.md

Producer-specificatie voor **QuantBuild** als bron van QuantLog-events.  
Implementatievolgorde van de hele stack staat in `QUANT_STACK_IMPLEMENTATION_SEQUENCE.md`; dit document beschrijft alleen **wat QuantBuild moet emitteren**.

Uitgewerkt logging-contract (velden en voorbeelden): `quantbuildv1/docs/QUANTBUILD_DECISION_LOGGING_SPEC.md`.

---

## Correlation (envelope)

Elk QuantBuild-event in één evaluatiecyclus deelt:

- `run_id`, `session_id`, `trace_id`
- `decision_cycle_id` (verplicht op decision-chain events)
- `symbol` waar van toepassing

Geen losse events zonder deze context als ze tot dezelfde cycle behoren.

---

## Decision chain (volgorde)

Per voltooide evaluatiecyclus (minimaal):

1. `signal_detected`
2. `signal_evaluated`
3. nul of meer `risk_guard_decision`
4. exact één terminaal `trade_action` (**ENTER**, **NO_ACTION**, **EXIT**, **REVERSE** volgens beleid)

**Geen silent exits:** elke cycle eindigt met `trade_action`. Geen return-pad dat de keten onderbreekt zonder terminal beslissing.

---

## Canonical reasons

- `trade_action` met `NO_ACTION`: alleen waarden uit het QuantLog-schema (`NO_ACTION_REASONS_*` in `quantlogv1`).
- `risk_guard_decision`: canonieke `reason` bij BLOCK; waar meetbaar `threshold` / `observed_value` / `session` / `regime` meesturen.
- `signal_detected`: gestructureerde velden (geen vrije-tekst “reason” als enige uitleg).

---

## Minimale payload-inhoud (blauwdruk)

- **`signal_evaluated`:** o.a. setup/context (`signal_type`, `confidence`), waar beschikbaar `session`, `regime`, `combo_count`, `price_at_signal`, `spread`.
- **`risk_guard_decision`:** `guard_name`, `decision`, `reason`; bij BLOCK meetbare context.
- **`trade_action`:** `decision`, `reason`; bij **ENTER** ook `trade_id` zodra bekend.

Execution-events (`order_*`, `trade_executed`, `trade_closed`) komen primair uit QuantBridge / broker-sync; QuantBuild kan `trade_executed` / `trade_closed` alleen emitteren waar de runtime dat expliciet ondersteunt (bijv. backtest).

---

## Validatie-alignment

QuantLog valideert o.a.:

- aanwezigheid verplichte payloadvelden per `event_type`
- monotone ketenorde per `decision_cycle_id`
- ENTER → `trade_id` en latere koppeling naar orders

---

## Deliverable (producer-MVP)

- Volledige decision trace per cycle met stabiele identifiers
- Geen ontbrekende `trade_action`
- Redenen en guard-telemetry uitsluitend via canonieke/gestructureerde velden
