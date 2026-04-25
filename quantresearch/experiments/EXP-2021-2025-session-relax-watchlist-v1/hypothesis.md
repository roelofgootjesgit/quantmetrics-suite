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
