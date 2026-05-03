# HYP-002 — Gesloten research-dossier (EXP-002)

**Status:** PROMOTION CANDIDATE — gevalideerd onder spread-stress en temporele splitsing.  
**Automatisch gegenereerd:** `2026-05-03T18:42:39.640992Z` uit pipeline-metrics (`metrics_bundle.json`).  
**Experiment:** `EXP-002` in `registry/experiments.json`.

---

## Finale spread-stress verificatie (mock_spread = 0.5)

| Check | Drempel | Resultaat | Status |
|-------|---------|-----------|--------|
| `mean_r` overall | > +0.028 | **+0.102** | ja |
| `mean_r` 2021–2023 | > 0 | **+0.071** | ja |
| `mean_r` 2024–2025 | > 0 | **+0.082** | ja |
| Temporele stabiliteit | Beide periodes positief | **+0.071** / **+0.082** | ja |
| `n` overall | ≥ 50 | **439** | ja |

*(Zie `variant_run_id` op EXP-002; ruwe metrics: `runs/hyp002-v5a-expansion-block-closed-2026/metrics_bundle.json`.)*

---

## Referentie — zelfde variant, default spread (0.2), 5y rolling

| Metriek | Waarde |
|---------|--------|
| `mean_r` overall | **+0.117** |
| `n` | **439** |

---

## Volledige onderzoeksroute — afgesloten

```
HYP-001 single-bar sweep (5j)
  → n=20 → REJECT_EVENT_FREQUENCY

HYP-002 baseline C=5, alle regimes
  → n=528, mean_r=+0.028 → VALIDATION_REQUIRED
  → V3 excl. expansion → +0.043 → VALIDATION_REQUIRED
  → V4 compression-only → +0.048 → REJECT promotie
  → Shadow-analyse → overlap-bias neutraal (delta +0.003)
  → V5A C=2 → +0.072, temporeel instabiel → PROMOTION INGETROKKEN
  → V5B M=3 → +0.015 → REJECT
  → V5A + expansion-block (spread 0.2) → +0.117, split stabiel
  → V5A + expansion-block (spread 0.5) → +0.102, split stabiel
  → PROMOTION CANDIDATE
```

---

## Gevalideerde configuratie

| Parameter | Waarde |
|-----------|--------|
| Engine | `ny_sweep_failure_reclaim` |
| C — max continuation | 2.0 points |
| N — failure window | 3 bars (45 min op M15) |
| M — reclaim window | 6 bars (90 min op M15) |
| Regime-filter | Expansion excluded |
| Sessie-filter | Geen (NY domineert natuurlijk) |
| Reference | London high/low 07:00–12:00 UTC |
| Sweep-window | 13:30–16:00 UTC |
| Spread-aanname (stress) | 0.5 points (conservatief) |

---

## Wat PROMOTION CANDIDATE wel en niet betekent

**Wel:** het mechanisme is aangetoond over twee onafhankelijke periodes, met voldoende sample size, zonder single-trade dominantie, onder conservatieve spread-aanname. De hypothese is niet verworpen.

**Niet:** bewijs van winstgevendheid in live trading. De volgende fase is een aparte onderzoeksvraag met andere vereisten.

---

## Verplicht vóór enige live implementatie

1. **Echte out-of-sample data** — C=2 is gekozen op 2021–2025; de split is temporele verificatie, geen echte OOS. Nieuwe data (bijv. 2026+) draaien zonder parameter-aanpassing.
2. **Slippage-model** — spread-correctie dekt halve spread op entry; SL-slippage (bijv. 1–3 points op volatiele bars) is niet gemodelleerd t.o.v. SL-buffer 5 points.
3. **Positie-sizing en drawdown-beleid** — fixed risk in backtest; live bepaalt sizing of historische drawdown-periodes dragelijk zijn.
4. **Paper trading** — minimaal 3 maanden op exacte engine-config vóór live kapitaal (executie-logica en fills, niet de edge zelf).

---

## Workflow (QuantResearch)

- Bundel reproducible metrics: `python -m quantresearch hyp002-pipeline`  
- Zie `docs/WORKFLOW_BACKTEST_NAAR_STRATEGIE.md` § HYP-002 gesloten dossier.
