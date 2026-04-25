# Experiment dossier: `EXP-2021-2025-session-relax-watchlist-v1`

Generated at (UTC): `2026-04-25T06:32:05.967388Z`

This file is assembled **only** from existing QuantResearch, QuantOS, and QuantAnalytics outputs. QuantResearch does **not** recompute trading metrics here.

## Auditor notice: discovery tiers are not promotion

- **WATCHLIST** is a throughput-compare triage label for follow-up experiment design. It is **not** production promotion.
- **RELAX_CANDIDATE** is a stricter triage label (per compare rules). It is **still not** promotion by itself.
- **PROMOTION** to production (or live deployment) requires an explicit **QuantOS promotion gate** outcome consistent with ledger rules; compare tables, clusters, and edge verdicts are evidence inputs, not promotion by themselves.

## 1. Experiment metadata

| Field | Value |
| --- | --- |
| experiment_id | EXP-2021-2025-session-relax-watchlist-v1 |
| title | Session / expansion relax watchlist follow-up (B0–B4) |
| status | completed |
| created_at_utc | 2026-04-25T06:00:00Z |
| completed_at_utc | 2026-04-25T05:56:08Z |
| matrix_type | session-relax-watchlist |
| hypothesis_summary | Split session/expansion relaxations (London expansion, NY-only, overlap timing, full session filter) after throughput discovery watchlisted session direction. |
| primary_metric | expectancy_R |
| promotion_decision (ledger) | VALIDATION_REQUIRED |
| discovery_tier (ledger) | watchlist |
| baseline_run_id | qb_run_20260425T055434Z_78f6ef7c |
| canonical_artifact_path | quantmetrics_os/runs/EXP-2021-2025-session-relax-watchlist-v1 |

## 2. Parent / rerun lineage

*No rerun lineage fields on this experiment (treat as primary ledger entry unless manually edited).*

## 3. Hypothesis

# Hypothesis

Prior matrix (`EXP-2021-2025-throughput-discovery-v1`) placed **session_filter** on the **discovery watchlist**: modest trade lift (~≥5% vs baseline) with expectancy > 0 and PF ≥ 1.25, but below the **relax-candidate** bar (>10% trades + material expectancy guardrails).

We hypothesize that **which session bucket is relaxed** matters: allowing expansion in London, widening NY-only timing, relaxing overlap hour gates, or turning off the pipeline session filter may differ in **throughput vs edge quality**.

## Success criteria (research, not promotion)

- Funnel deltas (`throughput.json`) show where signals reappear.
- Expectancy and PF do not collapse vs B0 on the same window.
- Drawdown vs B0 remains within the configured promotion-gate ratio where applicable.
- Promotion gate may still read `VALIDATION_REQUIRED`; that is acceptable for this experiment.

## Anti curve fitting

This matrix is **not** for answering “which session has the highest PF”. It is only for: **where does a controlled session/expansion opening add throughput without destroying edge shape vs B0?** Use compare `guards_to_relax_candidate` / `guards_to_watchlist` plus per-variant `promotion_decision.json`, not a single headline number.


## 4. Experiment plan

# Experiment plan

## QuantOS

Matrix preset: **`session-relax-watchlist`** (`throughput_discovery_matrix.py --matrix session-relax-watchlist`).

Generated configs: `quantbuild/configs/_throughput_discovery/<experiment_id>/B*.yaml`

Artifacts: `quantmetrics_os/runs/<experiment_id>/b*_*/` plus `THROUGHPUT_DISCOVERY_SUMMARY.md`, `throughput_discovery_registry.json`, `THROUGHPUT_COMPARE.{json,md}` (compare baseline defaults to **`b0_baseline`**).

Example:

```text
python quantmetrics_os/scripts/throughput_discovery_matrix.py ^
  --matrix session-relax-watchlist ^
  --experiment-id EXP-2021-2025-session-relax-watchlist-v1 ^
  --base-config configs/strict_prod_v2.yaml ^
  --start-date 2021-01-01 ^
  --end-date 2025-12-31
```

Or via orchestrator (subcommand name is still `throughput-discovery`; it forwards to the same script):

`python quantmetrics_os/orchestrator/quantmetrics.py experiments throughput-discovery --matrix session-relax-watchlist --experiment-id EXP-2021-2025-session-relax-watchlist-v1 -c configs/strict_prod_v2.yaml --start-date 2021-01-01 --end-date 2025-12-31`

## Variant intent (implementation mapping)

| Variant | Intent |
| --- | --- |
| B0 | Baseline control |
| B1 | Expansion `allowed_sessions` includes **London** (was NY+Overlap only in strict_prod_v2) |
| B2 | Expansion **New York only**; `min_hour_utc` set to **0** (relax NY window gate) |
| B3 | Expansion **New York + Overlap**; `min_hour_utc` **0** (relax overlap timing vs baseline 10) |
| B4 | `filters.session: false` — broadest session-side relax in this matrix |

Hard risk parameters in YAML (daily loss, equity kill, position limits, etc.) are **not** targets for relaxation in this plan.


## 5. Linked QuantOS artifacts

From `links.json` (paths resolved via `suite.suite_root` when relative):

```json
{
  "quantos_run_dir": "quantmetrics_os/runs/EXP-2021-2025-session-relax-watchlist-v1",
  "paths_are_absolute": false,
  "throughput_compare_json": "quantmetrics_os/runs/EXP-2021-2025-session-relax-watchlist-v1/THROUGHPUT_COMPARE.json",
  "throughput_compare_md": "quantmetrics_os/runs/EXP-2021-2025-session-relax-watchlist-v1/THROUGHPUT_COMPARE.md",
  "throughput_discovery_registry": "quantmetrics_os/runs/EXP-2021-2025-session-relax-watchlist-v1/throughput_discovery_registry.json",
  "throughput_discovery_summary": "quantmetrics_os/runs/EXP-2021-2025-session-relax-watchlist-v1/THROUGHPUT_DISCOVERY_SUMMARY.md"
}
```

- **QuantOS run root:** `C:\Users\Gebruiker\quantmetrics-suite\quantmetrics_os\runs\EXP-2021-2025-session-relax-watchlist-v1`
- ✓ **THROUGHPUT_COMPARE.json:** `C:\Users\Gebruiker\quantmetrics-suite\quantmetrics_os\runs\EXP-2021-2025-session-relax-watchlist-v1\THROUGHPUT_COMPARE.json`
- ✓ **THROUGHPUT_COMPARE.md:** `C:\Users\Gebruiker\quantmetrics-suite\quantmetrics_os\runs\EXP-2021-2025-session-relax-watchlist-v1\THROUGHPUT_COMPARE.md`
- ✓ **throughput_discovery_registry.json:** `C:\Users\Gebruiker\quantmetrics-suite\quantmetrics_os\runs\EXP-2021-2025-session-relax-watchlist-v1\throughput_discovery_registry.json`
- ✓ **THROUGHPUT_DISCOVERY_SUMMARY.md:** `C:\Users\Gebruiker\quantmetrics-suite\quantmetrics_os\runs\EXP-2021-2025-session-relax-watchlist-v1\THROUGHPUT_DISCOVERY_SUMMARY.md`
- **Registry variant rows:** 5

**Role folders (first-level under run root):**

- `b0_baseline/`
- `b1_london_only_relaxed/`
- `b2_ny_only_relaxed/`
- `b3_overlap_relaxed/`
- `b4_full_session_relaxed/`

## 6. Throughput compare (QuantAnalytics / QuantOS compare output)

- **Compare generated_at_utc:** `2026-04-25T06:05:45.267791Z`
- **Baseline folder:** `b0_baseline`
- **best_throughput_variant:** `b4_full_session_relaxed`
- **best_quality_variant:** `b4_full_session_relaxed`
- **best_balanced_variant:** `b4_full_session_relaxed`

| Variant | promotion (compare) | confidence | trades | exp R | PF | max DD R |
| --- | --- | --- | --- | --- | --- | --- |
| b0_baseline | VALIDATION_REQUIRED | LOW | 58 | 0.2931 | 1.5152 | 11.0 |
| b1_london_only_relaxed | VALIDATION_REQUIRED | LOW | 58 | 0.2931 | 1.5152 | 11.0 |
| b2_ny_only_relaxed | VALIDATION_REQUIRED | LOW | 55 | 0.2545 | 1.4375 | 11.0 |
| b3_overlap_relaxed | VALIDATION_REQUIRED | LOW | 58 | 0.2931 | 1.5152 | 11.0 |
| b4_full_session_relaxed | VALIDATION_REQUIRED | LOW | 63 | 0.4286 | 1.8182 | 10.0 |

**Compare notes (verbatim):**

- Rankings are heuristics for research triage; promotion still requires the hard gate.
- Do not promote on throughput alone; validate expectancy/PF/confidence and sample size.
- guards_to_relax_candidate and guards_to_watchlist are NOT promotion; see discovery_rule_summary.
- discovery_clusters is interpretive reading aid only; it does not change tier labels or promotion_decision.
- Avoid session curve fitting: interpret matrices as throughput vs quality trade-offs vs baseline, not best PF hunting.

## 7. Discovery tiers & clusters

### discovery_rule_summary

```json
{
  "version": "1.0",
  "scope": "All throughput discovery compare runs vs the selected baseline folder (A0\u2013A5, B0\u2013B4, future matrices).",
  "relax_candidate": {
    "trades": "strictly greater than baseline \u00d7 1.10 (>10% trade count)",
    "expectancy_r": "greater than or equal to baseline expectancy R minus 0.08 (material slack)",
    "profit_factor": "greater than or equal to 1.25",
    "max_drawdown_r": "variant / baseline ratio must be less than or equal to 1.20 (same order of magnitude as QuantOS promotion gate default)",
    "confidence": "ordinal must be greater than or equal to baseline (LOW < MEDIUM < HIGH); unknown fails"
  },
  "watchlist": {
    "trades": "greater than or equal to baseline \u00d7 1.05 (\u22655% trade count)",
    "expectancy_r": "strictly greater than 0",
    "profit_factor": "greater than or equal to 1.25",
    "notes": "No DD or confidence requirement; not promotion; use only for next experiment design."
  }
}
```

### watchlist_by_variant

- **`b4_full_session_relaxed`:** B4 pipeline session filter off: discovery watchlist vs `b0_baseline` (~8.6% trade lift, exp>0, PF≥1.25; does not meet full relax gates — not promotion)

### guards_to_watchlist

- B4 pipeline session filter off: discovery watchlist vs `b0_baseline` (~8.6% trade lift, exp>0, PF≥1.25; does not meet full relax gates — not promotion)

### guards_to_investigate

- daily_loss_cap
- equity_drawdown_kill_switch
- max_trades_per_session
- regime_allowed_sessions
- regime_profile

## 8. Promotion decisions (per variant, from compare JSON)

Values below are **QuantOS compare / gate labels** as recorded in THROUGHPUT_COMPARE.json, not an independent QuantResearch computation.

## 9. Edge verdicts (QuantAnalytics per variant)

| Variant folder | edge_verdict | confidence | main_risk (trunc.) |
| --- | --- | --- | --- |
| b0_baseline | VALIDATION_REQUIRED | LOW | Sample size too small to justify promotion |
| b1_london_only_relaxed | VALIDATION_REQUIRED | LOW | Sample size too small to justify promotion |
| b2_ny_only_relaxed | VALIDATION_REQUIRED | LOW | Sample size too small to justify promotion |
| b3_overlap_relaxed | VALIDATION_REQUIRED | LOW | Sample size too small to justify promotion |
| b4_full_session_relaxed | VALIDATION_REQUIRED | LOW | Sample size too small to justify promotion |

## 10. Final decision (QuantResearch)

# Decision

## Final Decision

VALIDATION_REQUIRED

## Reason

All B-variants including baseline show **LOW** confidence and **VALIDATION_REQUIRED** in `promotion_decision.json`. B4 adds a **watchlist** signal (+5 trades vs B0, exp > 0, PF ≥ 1.25) but does **not** meet relax-candidate thresholds (trade lift below the >10% bar vs B0; same confidence ordinal). No production promotion.

## What Passed

- B-matrix completed with QuantOS artifacts linked in `links.json`.
- Compare layer shows B4 on watchlist only; DD vs B0 acceptable on reported max_dd_R.

## What Failed

- No **relax-candidate** for B1–B4 vs B0 under canonical discovery gates.
- Promotion gate remains validation-only across variants.

## Discovery Signals

- **Relax candidates:** none.
- **Watchlist:** B4 full session relaxed (see `THROUGHPUT_COMPARE.json` / MD).
- **Clusters:** none (single watchlist variant in this run).

## Interpretation

Session pipeline off (B4) reproduces the prior A-matrix watchlist outcome magnitude; expansion-only tweaks (B1–B3) did not increase throughput on this sample. Further research should widen sample or deepen guard attribution before any config change.

## Next Action

**expand_sample** — increase representative decision cycles / address LOW confidence before another matrix; or **archive** if product scope shifts.

## Non-Negotiable Notes

- No promotion from watchlist.
- No promotion from LOW confidence.
- No promotion from small samples.


## 11. Next action

- **next_action (ledger):** `expand_sample`
- **next_experiment_id:** ``

### results_summary.md (excerpt)

# Results summary

**Status:** matrix + compare complete (2021-01-01 .. 2025-12-31).

Canonical outputs:

- `quantmetrics_os/runs/EXP-2021-2025-session-relax-watchlist-v1/THROUGHPUT_COMPARE.md`
- `quantmetrics_os/runs/EXP-2021-2025-session-relax-watchlist-v1/THROUGHPUT_COMPARE.json`
- Per variant: `analytics/promotion_decision.json`

## Headline vs B0 (same window)

| Variant | trades | exp (R) | PF | max_dd (R) | vs B0 |
| --- | ---: | ---: | ---: | ---: | --- |
| B0 | 58 | 0.29 | 1.52 | 11.0 | — |
| B1 London expansion | 58 | 0.29 | 1.52 | 11.0 | no throughput delta |
| B2 NY-only + hour relax | 55 | 0.25 | 1.44 | 11.0 | fewer trades |
| B3 overlap timing relax | 58 | 0.29 | 1.52 | 11.0 | no throughput delta |
| B4 session filter off | 63 | 0.43 | 1.82 | 10.0 | +5 trades; **watchlist** only (below >10% relax bar) |

## Compare interpretation

- **Relax-candidate (B1–B4):** none — B4 clears watchlist gates (≥5% trades, exp > 0, PF ≥ 1.25) but not the full relax set (needs **>**10% trades vs B0, DD/confidence rules per `THROUGHPUT_COMPARE`).
- **Anti curve fitting:** do not promote B4 because PF looks higher; treat as **throughput funnel signal** for the next single-variable design only.

