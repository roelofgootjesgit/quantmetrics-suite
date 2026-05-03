# Promotion Criteria

A strategy change can only be promoted if all conditions below are met.

## Hard rules

- `sample_size >= 100` closed trades
- Improvement vs baseline is consistent across time slices
- No single guard dominates more than `60%` of all BLOCK decisions
- Expectancy improvement is not explained by funnel/guard-pressure shifts alone
- Max drawdown stays within approved risk limits

## Why this exists

These rules keep QuantMetrics in a controlled baseline-vs-candidate discipline.
The goal is evidence-based promotion, not blind optimization.
