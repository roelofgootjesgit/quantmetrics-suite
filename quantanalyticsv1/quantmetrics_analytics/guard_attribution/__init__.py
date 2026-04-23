"""Guard Attribution MVP: QuantLog → blocks, context, slice counterfactuals, report."""

from __future__ import annotations

from quantmetrics_analytics.guard_attribution.pipeline import run_guard_attribution
from quantmetrics_analytics.guard_attribution.rerun_compare import compare_guard_rerun_runs

__all__ = ["run_guard_attribution", "compare_guard_rerun_runs"]
