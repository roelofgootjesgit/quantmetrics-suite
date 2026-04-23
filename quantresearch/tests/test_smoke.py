"""Smoke tests for QuantResearch MVP."""

import pytest

from quantresearch.comparison_engine import compare_runs
from quantresearch.decision_engine import decide_comparison


def test_compare_runs_example_from_spec():
    baseline = {"mean_r": -0.727, "trade_count": 11}
    variant = {"mean_r": 0.5, "trade_count": 8}
    out = compare_runs(
        baseline,
        variant,
        experiment_id="EXP-001",
        baseline_run_id="20260422_192631Z",
        variant_run_id="20260422_192633Z",
    )
    assert out["experiment_id"] == "EXP-001"
    assert out["delta"]["mean_r"] == pytest.approx(1.227)
    assert out["delta"]["trade_count"] == -3
    assert "decision" in out


def test_decide_negative_mean_r():
    b = {"mean_r": 0.5, "trade_count": 50}
    v = {"mean_r": -1.0, "trade_count": 50}
    dlt = {"mean_r": -1.5}
    assert decide_comparison(b, v, dlt) == "baseline_preferred"


def test_aliases_expectancy_r():
    baseline = {"expectancy_r": -0.727, "total_trades": 11}
    variant = {"mean_r": 0.5, "trade_count": 8}
    out = compare_runs(baseline, variant, experiment_id="EXP-X")
    assert out["baseline"]["mean_r"] == pytest.approx(-0.727)
    assert out["variant"]["mean_r"] == pytest.approx(0.5)
