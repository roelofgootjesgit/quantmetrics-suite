"""Gate mapping from inference_report.json fields."""

from __future__ import annotations

from quantresearch.inference_consumer import apply_inference_to_experiment


def test_apply_pass_pass():
    prereg = {"minimum_n": 10, "minimum_effect_size_r": 0.028}
    inf = {
        "sample": {"n": 400, "mean_r": 0.05},
        "confidence_interval": {"lower": 0.035, "ci_95_lower": 0.035},
        "verdict": {"statistical_significance": "PASS", "economic_significance": "PASS"},
    }
    u = apply_inference_to_experiment("EXP-002", prereg, inf)
    assert u["academic_status"] == "PASS"
    assert u["effective_status"] == "PROMOTE_FULL"


def test_apply_fail_stat():
    prereg = {"minimum_n": 10, "minimum_effect_size_r": 0.028}
    inf = {
        "sample": {"n": 400},
        "confidence_interval": {"lower": 0.04},
        "verdict": {"statistical_significance": "FAIL", "economic_significance": "PASS"},
    }
    u = apply_inference_to_experiment("EXP-002", prereg, inf)
    assert u["academic_status"] == "FAIL"
    assert u["effective_status"] == "GOVERNANCE_ONLY"


def test_apply_mean_above_floor_but_ci_lower_fails():
    """Point mean clears the economic floor but the CI lower bound does not."""
    prereg = {"minimum_n": 10, "minimum_effect_size_r": 0.028}
    inf = {
        "sample": {"n": 400, "mean_r": 0.05},
        "confidence_interval": {"lower": 0.011, "upper": 0.09},
        "verdict": {"statistical_significance": "PASS", "economic_significance": "PASS"},
    }
    u = apply_inference_to_experiment("EXP-002", prereg, inf)
    assert u["academic_status"] == "FAIL"
    assert u["effective_status"] == "GOVERNANCE_ONLY"
    assert "ci_95_lower" in (u.get("inference_reason") or "")


def test_apply_low_n_overrides_pass_verdict():
    prereg = {"minimum_n": 300}
    inf = {
        "sample": {"n": 50},
        "verdict": {"statistical_significance": "PASS", "economic_significance": "PASS"},
    }
    u = apply_inference_to_experiment("EXP-002", prereg, inf)
    assert u["academic_status"] == "INSUFFICIENT_N"


def test_apply_insufficient_n_verdict():
    prereg = {"minimum_n": 300}
    inf = {
        "sample": {"n": 50},
        "verdict": {"statistical_significance": "INSUFFICIENT_N", "economic_significance": "PENDING"},
    }
    u = apply_inference_to_experiment("EXP-002", prereg, inf)
    assert u["academic_status"] == "INSUFFICIENT_N"
