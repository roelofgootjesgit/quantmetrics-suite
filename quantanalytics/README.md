# quantanalytics

## SYSTEM IDENTITY

This module is part of the QuantMetrics suite.
- Canonical name: `quantanalytics`
- Role: Analysis Engine (read-only on QuantLog JSONL)

`quantanalytics` converts JSONL event streams into deterministic diagnostics and reports. It is downstream only: no broker calls, no order placement, and no log mutation.

---

## Core responsibility

- Read event data from `quantlog`-compatible JSONL.
- Generate text reports for funnel, no-trade reasons, performance, and regime behavior.
- Produce optional key-findings markdown and run summaries.
- Stay strictly read-only on source data.

Data flow: `quantbuild` / `quantbridge` -> `quantlog` -> `quantanalytics`.

---

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

---

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

---

## Documentation

- [docs/ANALYTICS_ARCHITECTURE.md](docs/ANALYTICS_ARCHITECTURE.md)
- [docs/ANALYTICS_SPRINT_PLAN.md](docs/ANALYTICS_SPRINT_PLAN.md)
- [docs/LIVE_VPS_AND_LOCAL_BACKTEST.md](docs/LIVE_VPS_AND_LOCAL_BACKTEST.md)

---

## Suite repositories (GitHub)

| Repo | Remote |
| --- | --- |
| `quantmetrics_os` | [roelofgootjesgit/quantmetrics_os](https://github.com/roelofgootjesgit/quantmetrics_os) |
| `quantbuild` | [roelofgootjesgit/QuantBuild-Signal-Engine](https://github.com/roelofgootjesgit/QuantBuild-Signal-Engine) |
| `quantbridge` | canonical module: `quantbridge` |
| `quantlog` | canonical module: `quantlog` |
| `quantanalytics` (**this**) | canonical module: `quantanalytics` |
