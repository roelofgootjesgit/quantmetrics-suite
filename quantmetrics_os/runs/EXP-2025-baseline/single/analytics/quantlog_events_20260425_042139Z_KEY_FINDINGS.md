# Key findings

Generated (UTC): **2026-04-25T04:21:39Z**

## Warnings

| Level | Code | Detail |
| --- | --- | --- |
| MEDIUM | `GUARD_DOMINANCE` | 'regime_allowed_sessions' accounts for 89% of BLOCK decisions (57/64). Risk lockdown may dominate throughput. |

## Headline

data/context integrity issues dominate interpretation; guards heavily shape flow; regime expectancy differs materially

## Top problems

- session: present on 100.0% of signal_evaluated rows (75 rows)
- setup_type: present on 100.0% of signal_evaluated rows (75 rows)
- regime: present on 100.0% of signal_evaluated rows (75 rows)

## Top edges

- trend: mean_r=-0.727 (n=11)

## Top blockers

- regime_allowed_sessions: 57 BLOCKs (89% of guard blocks)
- daily_loss_cap: 5 BLOCKs (8% of guard blocks)
- regime_profile: 1 BLOCKs (2% of guard blocks)

## System state

- Closed-trade expectancy (overall): mean_r=-0.727 over n=11
- Exit efficiency (median capture vs |MFE|): ~151%
- Raw funnel counts: detected=75, evaluated=75, ENTER/REVERSE=11

---

*Rule-based output only — same inputs yield the same Markdown. Fix upstream logging when HIGH warnings persist.*
