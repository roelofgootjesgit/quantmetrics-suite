# QuantMetrics Suite

[![CI](https://github.com/roelofgootjesgit/QuantMetrics-Suite/actions/workflows/ci.yml/badge.svg)](https://github.com/roelofgootjesgit/QuantMetrics-Suite/actions/workflows/ci.yml)

Modular Python-based trading infrastructure with separated decision, execution, immutable event logging, orchestration, analytics, and research decision layers.

## Suite modules

- `quantbuild`: decision engine and simulation configs
- `quantbridge`: execution and broker integration
- `quantlog`: immutable event logging (JSONL contracts)
- `quantanalytics`: read-only diagnostics and reporting
- `quantmetrics_os`: run artifacts, lifecycle, and orchestration glue
- `quantresearch`: hypothesis-driven experiments, comparisons, and research artifacts

## 2-minute demo

This repository includes a small deterministic demo that analyzes a sample QuantLog event file.
This demo does not prove profitability.
It demonstrates how the system evaluates decision quality, identifies bottlenecks, and produces evidence for or against edge.
All outputs are deterministic given the same input event file.

```bash
pip install -r requirements.txt
python run_demo.py
```

Expected output:

- event counts by type
- decision funnel summary
- guard attribution
- simple validation verdict

This demo does not claim strategy edge. It demonstrates the infrastructure loop:
decision events -> immutable logging -> analytics -> verdict.

## Strategy evaluation workflow

1. Run baseline.
2. Run candidate with one controlled change.
3. Compare runs using deterministic analytics.
4. Apply promotion criteria.
5. Accept or reject the change.

The system does not optimize strategies blindly.
It enforces controlled iteration and evidence-based promotion.
