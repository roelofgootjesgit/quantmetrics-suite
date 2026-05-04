"""Markdown helpers for inference ledger."""

from __future__ import annotations

from quantresearch.ledger_inference_markdown import (
    render_gate_b_section,
    render_inference_results_table,
)


def test_render_inference_results_table_with_sample():
    inf = {
        "sample": {"n": 10, "mean_r": 0.05, "std_r": 0.2, "median_r": 0.0},
        "hypothesis_test": {
            "test_used": "wilcoxon_signed_rank",
            "p_value": 0.01,
            "alpha": 0.05,
            "significant_at_alpha": True,
        },
        "confidence_interval": {
            "lower": 0.01,
            "upper": 0.1,
            "ci_95_lower": 0.01,
            "method": "bootstrap_bca",
        },
        "effect_size": {"cohens_d": 0.1, "interpretation": "negligible"},
        "verdict": {
            "statistical_significance": "PASS",
            "economic_significance": "FAIL",
            "minimum_effect_size_used": 0.028,
            "economic_rule": "ci_95_lower >= minimum_effect_size_r",
        },
    }
    md = render_inference_results_table(inf)
    assert "n (trade_closed)" in md
    assert "| 10 |" in md or " 10 " in md
    assert "wilcoxon" in md
    assert "0.01" in md
    assert "FAIL" in md


def test_render_gate_b_with_inference():
    inf = {
        "hypothesis_test": {"test_used": "t", "p_value": 0.2, "alpha": 0.05},
        "confidence_interval": {"ci_95_lower": -0.1},
        "verdict": {"statistical_significance": "FAIL", "economic_significance": "FAIL"},
    }
    md = render_gate_b_section(
        academic_status="FAIL",
        effective_status="GOVERNANCE_ONLY",
        inference_reason="x",
        pre_registration_valid=False,
        pre_registration_status="retrospective",
        inference=inf,
    )
    assert "academic_status" in md
    assert "ci_95_lower" in md
