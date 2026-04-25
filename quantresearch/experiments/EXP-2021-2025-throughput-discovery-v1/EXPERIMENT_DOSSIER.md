# Experiment dossier: `EXP-2021-2025-throughput-discovery-v1`

Generated at (UTC): `2026-04-25T06:32:11.775402Z`

This file is assembled **only** from existing QuantResearch, QuantOS, and QuantAnalytics outputs. QuantResearch does **not** recompute trading metrics here.

## Auditor notice: discovery tiers are not promotion

- **WATCHLIST** is a throughput-compare triage label for follow-up experiment design. It is **not** production promotion.
- **RELAX_CANDIDATE** is a stricter triage label (per compare rules). It is **still not** promotion by itself.
- **PROMOTION** to production (or live deployment) requires an explicit **QuantOS promotion gate** outcome consistent with ledger rules; compare tables, clusters, and edge verdicts are evidence inputs, not promotion by themselves.

## 1. Experiment metadata

| Field | Value |
| --- | --- |
| experiment_id | EXP-2021-2025-throughput-discovery-v1 |
| title | Throughput discovery matrix (session / regime / cooldown isolation) |
| status | completed |
| created_at_utc | 2026-04-25T05:36:00Z |
| completed_at_utc | 2026-04-25T05:41:20Z |
| matrix_type | throughput-discovery |
| hypothesis_summary | Isolate which non-risk filters (session, regime, cooldown) drive throughput vs strict_prod_v2 baseline without weakening hard risk guards. |
| primary_metric | expectancy_R |
| promotion_decision (ledger) | VALIDATION_REQUIRED |
| discovery_tier (ledger) | watchlist |
| baseline_run_id | qb_run_20260425T053826Z_7c56e609 |
| canonical_artifact_path | quantmetrics_os/runs/EXP-2021-2025-throughput-discovery-v1 |

## 2. Parent / rerun lineage

*No rerun lineage fields on this experiment (treat as primary ledger entry unless manually edited).*

## 3. Hypothesis

# Hypothesis

**Primary:** The session filter stack removes a large share of raw signals without a proportional increase in expectancy; relaxing session gates may recover throughput while keeping expectancy acceptable.

**Secondary:** Regime permission is protective for expectancy; relaxing it should *not* be promoted even if throughput rises.

**Tertiary:** Cooldown may be over-blocking relative to its protective value.

## Success criteria (research, not promotion)

- Trades / executed signals increase materially vs A0.
- Expectancy and PF do not degrade beyond agreed tolerances vs A0.
- Max drawdown (stability peak) does not worsen beyond baseline ratio used in the promotion gate.


## 4. Experiment plan

# Experiment plan

## Matrix (QuantOS)

Command (from `quantmetrics_os/orchestrator`):

```powershell
python quantmetrics.py experiments throughput-discovery `
  -c configs/strict_prod_v2.yaml `
  --start-date 2021-01-01 `
  --end-date 2025-12-31 `
  --experiment-id EXP-2021-2025-throughput-discovery-v1
```

## Variants

| Key | Intent |
|-----|--------|
| A0 | Baseline control |
| A1 | Session throughput test |
| A2 | Regime throughput test |
| A3 | Cooldown throughput test |
| A4 | Combined session+regime |
| A5 | Broader non-risk relaxation (still keeps hard risk stack defaults) |

## What to read after the run

1. `quantmetrics_os/runs/EXP-2021-2025-throughput-discovery-v1/THROUGHPUT_COMPARE.md`
2. `quantmetrics_os/runs/EXP-2021-2025-throughput-discovery-v1/THROUGHPUT_DISCOVERY_SUMMARY.md`
3. Per variant: `analytics/promotion_decision.json`


## 5. Linked QuantOS artifacts

From `links.json` (paths resolved via `suite.suite_root` when relative):

```json
{
  "quantos_run_dir": "quantmetrics_os/runs/EXP-2021-2025-throughput-discovery-v1",
  "paths_are_absolute": false,
  "throughput_compare_json": "quantmetrics_os/runs/EXP-2021-2025-throughput-discovery-v1/THROUGHPUT_COMPARE.json",
  "throughput_compare_md": "quantmetrics_os/runs/EXP-2021-2025-throughput-discovery-v1/THROUGHPUT_COMPARE.md",
  "throughput_discovery_registry": "quantmetrics_os/runs/EXP-2021-2025-throughput-discovery-v1/throughput_discovery_registry.json",
  "throughput_discovery_summary": "quantmetrics_os/runs/EXP-2021-2025-throughput-discovery-v1/THROUGHPUT_DISCOVERY_SUMMARY.md"
}
```

- **QuantOS run root:** `C:\Users\Gebruiker\quantmetrics-suite\quantmetrics_os\runs\EXP-2021-2025-throughput-discovery-v1`
- ✓ **THROUGHPUT_COMPARE.json:** `C:\Users\Gebruiker\quantmetrics-suite\quantmetrics_os\runs\EXP-2021-2025-throughput-discovery-v1\THROUGHPUT_COMPARE.json`
- ✓ **THROUGHPUT_COMPARE.md:** `C:\Users\Gebruiker\quantmetrics-suite\quantmetrics_os\runs\EXP-2021-2025-throughput-discovery-v1\THROUGHPUT_COMPARE.md`
- ✓ **throughput_discovery_registry.json:** `C:\Users\Gebruiker\quantmetrics-suite\quantmetrics_os\runs\EXP-2021-2025-throughput-discovery-v1\throughput_discovery_registry.json`
- ✓ **THROUGHPUT_DISCOVERY_SUMMARY.md:** `C:\Users\Gebruiker\quantmetrics-suite\quantmetrics_os\runs\EXP-2021-2025-throughput-discovery-v1\THROUGHPUT_DISCOVERY_SUMMARY.md`
- **Registry variant rows:** 6

**Role folders (first-level under run root):**

- `_generated_configs/`
- `a0_baseline/`
- `a1_session_relaxed/`
- `a2_regime_relaxed/`
- `a3_cooldown_relaxed/`
- `a4_session_regime_relaxed/`
- `a5_throughput_discovery/`

## 6. Throughput compare (QuantAnalytics / QuantOS compare output)

- **Compare generated_at_utc:** `2026-04-25T06:06:08.948673Z`
- **Baseline folder:** `a0_baseline`
- **best_throughput_variant:** `a1_session_relaxed`
- **best_quality_variant:** `a1_session_relaxed`
- **best_balanced_variant:** `a1_session_relaxed`

| Variant | promotion (compare) | confidence | trades | exp R | PF | max DD R |
| --- | --- | --- | --- | --- | --- | --- |
| a0_baseline | VALIDATION_REQUIRED | LOW | 58 | 0.2931 | 1.5152 | 11.0 |
| a1_session_relaxed | VALIDATION_REQUIRED | LOW | 63 | 0.4286 | 1.8182 | 10.0 |
| a2_regime_relaxed | VALIDATION_REQUIRED | LOW | 58 | 0.2931 | 1.5152 | 11.0 |
| a3_cooldown_relaxed | VALIDATION_REQUIRED | LOW | 58 | 0.2931 | 1.5152 | 11.0 |
| a4_session_regime_relaxed | VALIDATION_REQUIRED | LOW | 63 | 0.4286 | 1.8182 | 10.0 |
| a5_throughput_discovery | VALIDATION_REQUIRED | LOW | 63 | 0.4286 | 1.8182 | 10.0 |

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

- **`a1_session_relaxed`:** session_filter (A1): discovery watchlist vs `a0_baseline` (~8.6% trade lift, exp>0, PF≥1.25; does not meet full relax gates — not promotion)
- **`a4_session_regime_relaxed`:** session + regime (A4): discovery watchlist vs `a0_baseline` (~8.6% trade lift, exp>0, PF≥1.25; does not meet full relax gates — not promotion)
- **`a5_throughput_discovery`:** throughput discovery (A5): discovery watchlist vs `a0_baseline` (~8.6% trade lift, exp>0, PF≥1.25; does not meet full relax gates — not promotion)

### discovery_clusters

```json
[
  {
    "tier": "watchlist",
    "variants": [
      "a1_session_relaxed",
      "a4_session_regime_relaxed",
      "a5_throughput_discovery"
    ],
    "representative_metrics": {
      "total_trades": 63.0,
      "expectancy_r": 0.4285714285714302,
      "profit_factor": 1.8181818181818212,
      "max_drawdown_r": 10.0
    },
    "preferred_next_test": "a1_session_relaxed",
    "rationale": "`a1_session_relaxed` is the preferred next single-variable test among this cluster (lowest heuristic config-delta rank vs baseline; see VARIANT_CONFIG_DELTA_RANK in quantmetrics_os/scripts/discovery_clusters.py)."
  }
]
```

### guards_to_watchlist

- session + regime (A4): discovery watchlist vs `a0_baseline` (~8.6% trade lift, exp>0, PF≥1.25; does not meet full relax gates — not promotion)
- session_filter (A1): discovery watchlist vs `a0_baseline` (~8.6% trade lift, exp>0, PF≥1.25; does not meet full relax gates — not promotion)
- throughput discovery (A5): discovery watchlist vs `a0_baseline` (~8.6% trade lift, exp>0, PF≥1.25; does not meet full relax gates — not promotion)

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
| a0_baseline | VALIDATION_REQUIRED | LOW | Sample size too small to justify promotion |
| a1_session_relaxed | VALIDATION_REQUIRED | LOW | Sample size too small to justify promotion |
| a2_regime_relaxed | VALIDATION_REQUIRED | LOW | Sample size too small to justify promotion |
| a3_cooldown_relaxed | VALIDATION_REQUIRED | LOW | Sample size too small to justify promotion |
| a4_session_regime_relaxed | VALIDATION_REQUIRED | LOW | Sample size too small to justify promotion |
| a5_throughput_discovery | VALIDATION_REQUIRED | LOW | Sample size too small to justify promotion |

## 10. Final decision (QuantResearch)

# Decision

## Final Decision

VALIDATION_REQUIRED

## Reason

Baseline and variants remain **LOW** confidence with **under 100** trades in the 2021–2025 window on this config. QuantOS promotion gate outputs `VALIDATION_REQUIRED` for all variants. Throughput discovery shows a **watchlist**-level session signal (A1/A4/A5 cluster) but **no relax-candidate** (trade count does not exceed baseline ×1.10 with full relax gates). Per ledger rules, this cannot be promoted.

## What Passed

- Full matrix executed with canonical QuantLog → analytics → compare → clusters.
- Hard risk stack unchanged across variants.
- Watchlist cluster identifies **A1_SESSION_RELAXED** as preferred next single-variable test when metrics tie (see `THROUGHPUT_COMPARE` discovery_clusters).

## What Failed

- Promotion gate: sample size / confidence blocks production promotion.
- No variant met **relax-candidate** tier (including DD and confidence vs baseline).

## Discovery Signals

- **Relax candidates:** none.
- **Watchlist:** A1 / A4 / A5 (clustered in compare MD; full strings in JSON).
- **Clusters:** one watchlist cluster; `preferred_next_test` = `a1_session_relaxed` (A1_SESSION_RELAXED).

## Interpretation

Session-related relaxations move the funnel modestly but evidence is insufficient for promotion. Regime-only and cooldown-only variants did not separate from baseline on this run. Next step is a narrower session experiment (see `next_experiment_id`).

## Next Action

Run **EXP-2021-2025-session-relax-watchlist-v1** (B-matrix) to isolate which session/expansion opening moves throughput without breaking quality shape.

## Non-Negotiable Notes

- No promotion from watchlist.
- No promotion from LOW confidence.
- No promotion from small samples.


## 11. Next action

- **next_action (ledger):** `isolate_guard`
- **next_experiment_id:** `EXP-2021-2025-session-relax-watchlist-v1`

### results_summary.md (excerpt)

# Results summary

**Status:** matrix + compare complete. Canonical outputs under QuantOS:

- `quantmetrics_os/runs/EXP-2021-2025-throughput-discovery-v1/THROUGHPUT_DISCOVERY_SUMMARY.md`
- `quantmetrics_os/runs/EXP-2021-2025-throughput-discovery-v1/throughput_discovery_registry.json`
- `quantmetrics_os/runs/EXP-2021-2025-throughput-discovery-v1/THROUGHPUT_COMPARE.md`
- `quantmetrics_os/runs/EXP-2021-2025-throughput-discovery-v1/THROUGHPUT_COMPARE.json`
- Per variant: `analytics/promotion_decision.json`, `PROMOTION_DECISION.md`

## Headline numbers (vs A0 baseline)

| Variant | trades | exp (R) | PF | max_dd (R) | Δ trades | Δ exp | Δ PF | dd / baseline |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| a0_baseline | 58 | 0.29 | 1.52 | 11.0 | 0 | 0 | 0 | 1.0 |
| a1_session_relaxed | 63 | 0.43 | 1.82 | 10.0 | +5 | +0.14 | +0.30 | 0.91 |
| a2_regime_relaxed | 58 | 0.29 | 1.52 | 11.0 | 0 | 0 | 0 | 1.0 |
| a3_cooldown_relaxed | 58 | 0.29 | 1.52 | 11.0 | 0 | 0 | 0 | 1.0 |
| a4_session_regime_relaxed | 63 | 0.43 | 1.82 | 10.0 | +5 | +0.14 | +0.30 | 0.91 |
| a5_throughput_discovery | 63 | 0.43 | 1.82 | 10.0 | +5 | +0.14 | +0.30 | 0.91 |

Automated triage (heuristic): `best_throughput_variant`, `best_quality_variant`, and `best_balanced_variant` all point to **a1_session_relaxed** (tied with a4/a5 on metrics in this run).

## Relax candidate vs discovery watchlist

QuantOS compare output splits **strong** vs **weak** discovery (promotion rules unchanged):

| Layer | Meaning | This run |
| --- | --- | --- |
| `guards_to_relax_candidate` | Canonical gates in `discovery_rule_summary` inside `THROUGHPUT_COMPARE.json` (trades >10% vs baseline, exp slack, PF, **DD ratio**, **confidence**) | **none** (+5/58 is below 10% trade-count bar) |
| `guards_to_watchlist` | Same JSON: ≥5% trade lift, exp > 0, PF ≥ 1.25 (no DD/confidence bar) | **A1, A4, A5** — full strings in JSON; **MD** collapses to one **Discovery Clusters** block with `preferred_next_test` |
| `discovery_clusters` | Interpretive only; same tier + near-identical trades/exp/PF/DD | One **watchlist** cluster → preferred next test **`A1_SESSION_RELAXED`** |

Follow-up matrix: **EXP-2021-2025-session-relax-watchlist-v1** (B0–B4: London expansion, NY-only, overlap timing, full session filter off) — see `quantresearch/experiments/EXP-2021-2025-session-relax-watchlist-v1/` and QuantOS `--matrix session-relax-watchlist`.

## Interpretation (research, not promotion)

- **Session relaxation (A1)** increased executed trades modestly (+5) with higher expectancy and PF in this sample; max drawdown improved vs baseline on the reported metric. All variants still show **confidence LOW** and **VALIDATION_REQUIRED** at the promotion gate — do not treat this as production promotion. The **watchlist** flags the session direction for a **narrower** next matrix, not for relaxing the promotion gate.
- **Regime-only (A2)** and **cooldown-only (A3)** did not change funnel or trade counts vs baseline on this config and window — the bottleneck is likely elsewhere, or those knobs are already aligned with baseline for this strategy.
- **A4/A5** match A1 on the table: combined or broader relaxations did not add incremental throughput beyond the session change in this run.

## Next research step

Hold a single-variable follow-up only after confirming event coverage and guard-attribution stability for the LOW confidence flag (e.g. more cycles, longer window, or explicit counterfactual diagnostics).

