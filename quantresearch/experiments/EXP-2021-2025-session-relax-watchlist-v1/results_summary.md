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
