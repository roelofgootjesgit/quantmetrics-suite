# HYP-002 — Hypothese

## Verhaal (mechanisme)

Na een London liquidity sweep die als *failure* wordt geclassificeerd (beperkte continuation), levert reclaim binnen M bars positieve expectancy wanneer expansion-regime trades worden uitgesloten en continuation-cap C=2 (V5A) wordt toegepast.

## Pre-registratie (v1)

- **Status:** `retrospective_reconstruction` — `pre_registration_valid` = **False** (geen wetenschappelijke pre-reg zolang retrospectief).
- **Eerlijkheidsnotitie (`note`):** Filed after EXP-002 completion. HYP-002 is NOT pre-registered. This file serves as template/baseline for future experiments only. minimum_n and effect thresholds were not chosen independently of observed outcomes (HARKing risk if mislabeled as pre-registration).

Machine-leesbaar: `preregistration.json` (kopie van `pipelines/hyp002_preregistration.json`).

- **Timestamp (UTC):** `2026-05-03T12:00:00Z`
- **locked_at_utc:** `2026-05-04T10:00:00Z`
- **alpha:** 0.05
- **minimum_n:** 300
- **minimum_effect_size_r:** 0.028
- **target_power:** 0.8

### H0 (nulhypothese)

Expectancy per trade (R) is at or below zero under the stated backtest: XAUUSD M15, ny_sweep_failure_reclaim V5A + expansion-block, broker.mock_spread 0.5, calendar window 2021-01-01 to 2025-12-31.

### H1 (alternatief)

Expectancy per trade (R) is strictly greater than +0.028 (pre-specified economic floor aligned with internal promotion gate).

### Testplan

Planned inferential layer (not yet automated in pipeline): one-sided test of mean R > 0; bootstrap 95% CI on mean R; Cohen d on per-trade R; Wilcoxon signed-rank vs 0 if non-Gaussian; rolling expectancy stability. Requires persisted per-trade R series from QuantBuild/QuantLog.


*Governance verdict (PROMOTION CANDIDATE) used descriptive gates on aggregated metrics. Academic PASS on statistical_significance is pending implementation of Pijler 2 outputs.*
