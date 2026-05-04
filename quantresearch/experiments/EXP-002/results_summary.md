# Resultaten (samenvatting)

## Descriptief (aggregaten)

- **Overall mock_spread 0.5:** expectancy_r **0.102**, n=439
- **2021–2023 @0.5:** 0.071, n=246
- **2024–2025 @0.5:** 0.082, n=186

Volledige metrics: `quantresearch/runs/hyp002-v5a-expansion-block-closed-2026/metrics_bundle.json`.

## Inferentie (academische laag)

| Statistiek | Waarde |
|------------|--------|
| Bron | QuantAnalytics `inference_report.json` (schema `inference_v1`) |
| n (trade_closed) | 439 |
| mean_r (descriptief) | 0.117074 |
| std_r / median_r | 1.441169 / -1.000000 |
| Test gebruikt | wilcoxon_signed_rank |
| p-waarde (two-sided vs H0 median R=0) | 3.82871e-05 (PASS bij α=0.05) |
| 95% CI mean R (bootstrap) | [-0.018153, 0.252362] — method: bootstrap_bca |
| Economische gate | ci_95_lower -0.018153 vs floor 0.028 → **FAIL** (`ci_95_lower >= minimum_effect_size_r`) |
| Cohen's d (trade-R) | 0.081236 (negligible) |
| Statistisch verdict | **PASS** |
| Economisch verdict | **FAIL** |

Zie `docs/ACADEMIC_RESEARCH_PROTOCOL.md` en `experiment.json` voor governance vs academische status.
