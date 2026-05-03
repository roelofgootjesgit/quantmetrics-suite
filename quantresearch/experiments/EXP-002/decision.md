# Besluit

## Final Decision

Zie ook **twee gescheiden statusvelden** in `experiment.json`: `governance_status`, `academic_status`, `effective_status`.

### Gate A — Governance (descriptief)

**`governance_status`: PROMOTE** — interne criteria gehaald (aggregaten, spread-stress, temporele split). Zie `results_summary.md` en `research_logs/HYP-002_EXP-002_closed_dossier.md`.

### Gate B — Academisch (inferentie)

**`academic_status`: PENDING** — geen p-waarde / bootstrap-CI / Cohen d op per-trade R; `preregistration.json` is **retrospectief** (`pre_registration_valid: false`). Geen `PROMOTE_FULL` zolang Gate B niet PASS is (zie `docs/ACADEMIC_RESEARCH_PROTOCOL.md`).

### Effectieve status

**`effective_status`:** `GOVERNANCE_ONLY — not academically validated`

Architectuurregel: promoveer nooit naar fases die academische eisen stellen zonder expliciete PASS op beide gates.

Dit is geen live-tradingbewijs; volgende fase: OOS-data, slippage-model, sizing, paper trading.
