# Case Study: Demo Run Evaluation

## Setup

- dataset: `examples/demo_quantlog_events.jsonl`
- system mode: baseline dry-run demonstration
- trades: 1 closed trade in sample

## Findings

- Funnel is complete (`detected -> evaluated -> action -> filled -> closed`) with deterministic counts.
- Current sample has no blocking guard events, so guard dominance is currently `none (0% of blocks)`.
- Trade performance is positive in this tiny sample (`expectancy +1.20R`, `profit factor inf`, `winrate 100%`).
- Verdict is `VALIDATION_REQUIRED` because sample size is below institutional review threshold.

## Conclusion

System shows end-to-end observability and evaluation mechanics, but the sample is too small to validate edge.

## Next experiment

- Expand sample to multiple decision cycles with both wins and losses.
- Include explicit guard block scenarios (for example cooldown/risk block paths) to quantify dominance.
- Re-run the same event window and compare funnel conversions, guard dominance, and expectancy.
