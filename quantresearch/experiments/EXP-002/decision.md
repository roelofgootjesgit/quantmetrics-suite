# Besluit

## Final Decision

Zie ook **twee gescheiden statusvelden** in `experiment.json`: `governance_status`, `academic_status`, `effective_status`.

### Gate A — Governance (descriptief)

**`governance_status`: PROMOTE** — interne criteria gehaald (aggregaten, spread-stress, temporele split). Zie `results_summary.md` en `research_logs/HYP-002_EXP-002_closed_dossier.md`.

### Gate B — Academisch (inferentie)

`preregistration.json`: **retrospectief** (`pre_registration_valid`: **False**, status `retrospective_reconstruction`).

**`academic_status`:** **FAIL**  
**`effective_status`:** `GOVERNANCE_ONLY`  

- **Test:** `wilcoxon_signed_rank`  
- **p-waarde:** 3.82871e-05 → statistisch **PASS** (α = 0.05)  
- **ci_95_lower (mean R):** -0.018153 → economisch **FAIL** (vloer = 0.028 R)  
- **Reden (consumer):** economic_gate=ci_95_lower(-0.018153)<minimum_effect_size_r(0.028)

Geen `PROMOTE_FULL` zonder PASS op **beide** gates (statistisch én economisch volgens CI-ondergrens).


### Effectieve status

**`effective_status`:** `GOVERNANCE_ONLY`  
**`academic_status`:** **FAIL**

Architectuurregel: promoveer niet naar fases die academische eisen stellen zonder expliciete PASS op beide gates.

Dit is geen live-tradingbewijs; volgende fase: OOS-data, slippage-model, sizing, paper trading.
