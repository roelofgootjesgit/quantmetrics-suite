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
