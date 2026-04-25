# quantanalytics

Analysis module for the QuantMetrics Suite.

`quantanalytics` is the read-only diagnostics layer that turns QuantLog event streams into deterministic evidence for strategy evaluation decisions.

## System identity

- Canonical name: `quantanalytics`
- Suite role: Analysis Engine (downstream from `quantlog`)
- Boundary: reads events, computes diagnostics, writes reports; never places orders or mutates source logs

## Why this module exists

`quantbuild` and `quantbridge` create decisions and execution events.
`quantlog` stores those events as immutable JSONL.
`quantanalytics` answers: what happened, where opportunity was lost, and whether observed results are stable enough to justify promotion.

Core outputs include:

- funnel diagnostics (detected -> evaluated -> action -> filled -> closed)
- no-trade and guard-related bottleneck insights
- performance and regime summaries
- key findings artifacts for human review

Data flow: `quantbuild` / `quantbridge` -> `quantlog` -> `quantanalytics` -> `quantresearch` / promotion decisions.

## Correlation contract in the suite

`quantanalytics` relies on the same correlation keys emitted upstream:

- `run_id`: identifies one run artifact set
- `session_id`: groups related runtime sessions inside a run
- `trace_id`: links end-to-end execution traces
- `decision_cycle_id`: links decision-chain events (`signal_detected` -> `trade_action`)
- `trade_id` / `order_ref`: links execution and lifecycle events

Without these keys, diagnostics can still run, but decision attribution quality drops.

## Repository layout

```text
quantanalytics/
├── quantmetrics_analytics/
│   ├── ingestion/
│   ├── processing/
│   ├── transforms/
│   ├── analysis/
│   └── cli/
├── docs/
├── tests/
├── pyproject.toml
└── README.md
```

Package and CLI:
- Package name: `quantmetrics-analytics`
- Import: `quantmetrics_analytics`
- CLI: `python -m quantmetrics_analytics.cli.run_analysis` or `quantmetrics-analytics`

## Quick start

Install:

```bash
cd quantanalytics
pip install -e .
```

Run on one file:

```bash
python -m quantmetrics_analytics.cli.run_analysis \
  --jsonl /path/to/events.jsonl \
  --reports all
```

Run on a directory:

```bash
python -m quantmetrics_analytics.cli.run_analysis \
  --dir /path/to/quantlog_day_folder \
  --reports summary,no-trade,funnel
```

Use exactly one input mode: `--jsonl`, `--dir`, or `--glob`.

Default output location:

```text
quantanalytics/output_rapport/<input_stem>_YYYYMMDD_HHMMSSZ.txt
quantanalytics/output_rapport/<input_stem>_YYYYMMDD_HHMMSSZ_KEY_FINDINGS.md
```

## Documentation

- [docs/ANALYTICS_ARCHITECTURE.md](docs/ANALYTICS_ARCHITECTURE.md)
- [docs/ANALYTICS_SPRINT_PLAN.md](docs/ANALYTICS_SPRINT_PLAN.md)
- [docs/LIVE_VPS_AND_LOCAL_BACKTEST.md](docs/LIVE_VPS_AND_LOCAL_BACKTEST.md)

## In the full QuantMetrics system

- Upstream modules produce decisions/events: `quantbuild`, `quantbridge`, `quantlog`
- This module transforms those events into deterministic diagnostics
- Downstream consumers use these artifacts for research and governance (`quantresearch`, promotion gates, run reviews)

This module is intentionally analysis-only: it improves decision quality visibility, not trade execution.
