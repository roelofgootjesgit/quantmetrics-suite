# quantresearch

## SYSTEM IDENTITY

This module is part of the QuantMetrics suite.
- Canonical name: `quantresearch`
- Role: Research and Decision Layer

`quantresearch` captures hypothesis-driven strategy research: what was tested, what was learned, and what should change next.

---

## Core responsibility

- Register experiments and link baseline/variant runs.
- Compare run metrics and generate decision-oriented artifacts.
- Store validated edges and rejected hypotheses as knowledge files.
- Keep a living research index for portfolio-level strategy learning.

## Correlation with the total system

`quantresearch` depends on consistent run correlation generated upstream:

- links baseline and candidate by experiment IDs and run IDs
- consumes analytics and event-derived metrics tied to `run_id`, `trace_id`, and decision/execution outcomes
- turns correlated artifacts into explicit promotion/reject decisions

In short: upstream modules produce correlated evidence; `quantresearch` converts that evidence into governance decisions.

---

## Where it sits

```text
QuantBuild      → simulation & configs
QuantBridge     → execution
QuantLog        → source of truth (events)
QuantAnalytics  → diagnostics (“what happened”)
QuantResearch   → decisions & reproducible research (“what it means”)
```

Typical loop:

```text
Hypothesis → Build variant → Backtest / run → Metrics & analytics
    → Compare to baseline → Conclusion → Decision → Update knowledge base
```

---

## Features

| Area | What this repo provides |
|------|-------------------------|
| **Experiment registry** | Central `registry/experiments.json` — one record per study (`EXP-xxx`), configs, run IDs, status, outcome |
| **Comparison** | Normalizes metric dicts from backtest/analytics JSON, computes deltas, applies rule-based hints (`comparison_engine`, `decision_engine`) |
| **Artifacts** | `comparisons/<EXP>_comparison.{json,md}` |
| **Research logs** | Markdown logs from templates under `research_logs/` |
| **Knowledge** | `confirmed_edges.json`, `rejected_hypotheses.json`, structured edges in `edge_registry` |
| **Living index** | Run `write_research_index()` to refresh `docs/RESEARCH_INDEX.md` from the registries |

Design rules baked in: **one hypothesis per experiment**, **same data window** for baseline and variant, **baseline required**, **run IDs** tied to real artifacts, conclusions traceable to numbers.

---

## Install

From the repository root:

```bash
pip install -e ".[dev]"   # dev: pytest
```

Requires **Python 3.10+**. No runtime dependencies beyond the standard library.

If you import the package from another working directory, set:

```bash
set QUANTRESEARCH_ROOT=C:\path\to\quantresearch   # Windows
export QUANTRESEARCH_ROOT=/path/to/quantresearch   # Unix
```

---

## Quick start

**1.** Export baseline and variant metrics as JSON (from QuantBuild scripts, analytics, or hand-built dicts). Keys like `mean_r` / `expectancy_r`, `trade_count` / `total_trades` are normalized automatically.

**2.** Compare and write artifacts:

```python
from pathlib import Path
from quantresearch.comparison_engine import (
    compare_runs,
    write_comparison_artifacts,
    load_json_metrics,
)

baseline = load_json_metrics(Path("artifacts/baseline_metrics.json"))
variant = load_json_metrics(Path("artifacts/variant_metrics.json"))

cmp = compare_runs(
    baseline,
    variant,
    experiment_id="EXP-001",
    baseline_run_id="20260422_192631Z",
    variant_run_id="20260422_192633Z",
)
write_comparison_artifacts(cmp)
```

**3.** Record or update experiments via `quantresearch.experiment_registry` (`upsert_experiment`, etc.).

**4.** Refresh the markdown dashboard generated from registries:

```python
from quantresearch.markdown_renderer import write_research_index

write_research_index()
```

**5.** Optional: build a research log with `quantresearch.research_log_builder` (`build_research_log_markdown`, `write_research_log`).

---

## Documentation

| Document | Description |
|----------|-------------|
| [docs/WORKFLOW_BACKTEST_NAAR_STRATEGIE.md](docs/WORKFLOW_BACKTEST_NAAR_STRATEGIE.md) | **NL** — end-to-end workflow from backtest to strategy decisions |
| [docs/RESEARCH_INDEX.md](docs/RESEARCH_INDEX.md) | Auto-generated snapshot of experiments, edges, and rejected hypotheses |

---

## Repository layout

```text
quantresearch/           # Python package (installable)
registry/               # experiments.json, confirmed_edges.json, rejected_hypotheses.json
schemas/                # JSON Schema for experiments / research logs
research_logs/          # Human-readable STRATEGY RESEARCH LOG files
comparisons/            # JSON + Markdown comparison artifacts
templates/              # Markdown templates for logs and comparisons
tests/                  # pytest
docs/                   # Workflow guide + generated RESEARCH_INDEX.md
```

---

## Running tests

```bash
py -3 -m pytest -q
```

---

## Suite repositories (GitHub)

| Repo | Remote |
| --- | --- |
| `quantmetrics_os` | [roelofgootjesgit/quantmetrics_os](https://github.com/roelofgootjesgit/quantmetrics_os) |
| `quantbuild` | [roelofgootjesgit/QuantBuild-Signal-Engine](https://github.com/roelofgootjesgit/QuantBuild-Signal-Engine) |
| `quantbridge` | canonical module: `quantbridge` |
| `quantlog` | canonical module: `quantlog` |
| `quantresearch` (**this**) | [QuantResearch-Decision-Engine](https://github.com/roelofgootjesgit/QuantResearch-Decision-Engine) |

---

## Remote

Upstream for this decision-engine line: [QuantResearch-Decision-Engine](https://github.com/roelofgootjesgit/QuantResearch-Decision-Engine) on GitHub.

---

## Summary

QuantResearch is not a loose notebook: it is a **small research machine** — registry, comparison, logs, and knowledge files so strategy iteration stays **auditable** and **comparable** across experiments.
