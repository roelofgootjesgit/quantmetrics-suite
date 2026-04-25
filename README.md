# QuantMetrics Suite

[![CI](https://github.com/roelofgootjesgit/QuantMetrics-Suite/actions/workflows/ci.yml/badge.svg)](https://github.com/roelofgootjesgit/QuantMetrics-Suite/actions/workflows/ci.yml)

This repository shows how to evaluate trading systems - not the proprietary strategies themselves.

> We don't claim edge - we build the system that proves it.

QuantMetrics Suite is a modular Python-based trading infrastructure for evaluating strategy decisions under controlled, reproducible conditions.

It separates decision logic, execution, event logging, orchestration, analytics, and research so that every trading decision can be traced, replayed, analyzed, and either promoted or rejected based on evidence.

This is not a trading bot, signal service, or profitability claim.
It is an evaluation system for testing whether a strategy survives real operational constraints.

## What this system is designed to answer

QuantMetrics is built around questions that matter in systematic trading:

- Did the strategy produce a valid decision?
- Was the decision blocked by risk, regime, session, or execution constraints?
- Where in the funnel was opportunity lost?
- Did performance improve because the signal improved, or because filtering was relaxed?
- Is the result stable enough to promote, or only noise from a small sample?

## Core design principles

- Separation between decision and execution
- Immutable event logging as source of truth
- Deterministic analytics from fixed input data
- Baseline-vs-candidate comparison before promotion
- Explicit rejection of unproven edge
- Research artifacts that can be reviewed after the run

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

## License and usage

This repository is open-source under the MIT License.

The code demonstrates infrastructure and evaluation design principles.
It does not include proprietary research configurations, datasets, or production deployment setups.
