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
