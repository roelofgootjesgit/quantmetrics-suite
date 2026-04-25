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
