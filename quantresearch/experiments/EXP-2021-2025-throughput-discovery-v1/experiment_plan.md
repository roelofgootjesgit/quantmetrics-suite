# Experiment plan

## Matrix (QuantOS)

Command (from `quantmetrics_os/orchestrator`):

```powershell
python quantmetrics.py experiments throughput-discovery `
  -c configs/strict_prod_v2.yaml `
  --start-date 2021-01-01 `
  --end-date 2025-12-31 `
  --experiment-id EXP-2021-2025-throughput-discovery-v1
```

## Variants

| Key | Intent |
|-----|--------|
| A0 | Baseline control |
| A1 | Session throughput test |
| A2 | Regime throughput test |
| A3 | Cooldown throughput test |
| A4 | Combined session+regime |
| A5 | Broader non-risk relaxation (still keeps hard risk stack defaults) |

## What to read after the run

1. `quantmetrics_os/runs/EXP-2021-2025-throughput-discovery-v1/THROUGHPUT_COMPARE.md`
2. `quantmetrics_os/runs/EXP-2021-2025-throughput-discovery-v1/THROUGHPUT_DISCOVERY_SUMMARY.md`
3. Per variant: `analytics/promotion_decision.json`
