# QuantResearch

QuantResearch is the hypothesis and decision layer on top of QuantAnalytics outputs.

**Stack:** QuantBuild → QuantBridge → QuantLog → QuantAnalytics → **QuantResearch**.

**Loop:** Hypothesis → Variant → Backtest/run → Analytics → Compare to baseline → Conclusion → Decision → Knowledge base.

**Handleiding (backtest → strategy):** zie `docs/WORKFLOW_BACKTEST_NAAR_STRATEGIE.md`.

## Usage (Python)

```python
from pathlib import Path
from quantresearch.comparison_engine import compare_runs, write_comparison_artifacts, load_json_metrics
from quantresearch.experiment_registry import upsert_experiment
from quantresearch.markdown_renderer import write_readme

cmp = compare_runs(load_json_metrics(Path('baseline.json')), load_json_metrics(Path('variant.json')), experiment_id='EXP-001')
write_comparison_artifacts(cmp)
write_readme()
```

Environment: set `QUANTRESEARCH_ROOT` if the package is imported from outside the repo root.

## Experiments

| ID | Date | Title | Result | Status |
|----|------|-------|--------|--------|
| EXP-001 | 2026-04-22 | Expansion-only regime test | positive | completed |

## Confirmed edges

- Expansion regime shows positive expectancy in Q1 2026 backtest.

## Rejected hypotheses

- Trend regime is profitable in the tested Q1 2026 baseline.

## Open questions

- _(none tracked in generator — edit README or pass open_questions)_

## Next experiments

- EXP-002 Expansion × session filtering
- EXP-003 Expansion-only with regime_allowed_sessions relaxed
