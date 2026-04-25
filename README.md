# QuantMetrics Suite

[![CI](https://github.com/roelofgootjesgit/QuantMetrics-Suite/actions/workflows/ci.yml/badge.svg)](https://github.com/roelofgootjesgit/QuantMetrics-Suite/actions/workflows/ci.yml)

Modular Python-based trading infrastructure with separated decision, execution, immutable event logging, orchestration, and analytics layers.

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
