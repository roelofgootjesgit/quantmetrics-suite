from __future__ import annotations

from quantanalytics.guard_attribution.verdict import create_edge_verdict


def test_edge_verdict_low_sample():
    guard_attribution = {
        "guards": [
            {
                "guard_name": "spread_guard",
                "verdict": "EDGE_PROTECTIVE",
                "sample_quality": "INSUFFICIENT_DATA",
            }
        ]
    }
    stability = {"regime": [{"verdict": "PROMISING_BUT_WEAK"}]}
    decision_quality = [{"run_id": "qb_run_20260425T042136Z_dbd1b0cc", "quality_score": 1, "quality_label": "MEDIUM_QUALITY"}]
    warnings = []

    verdict = create_edge_verdict(guard_attribution, stability, decision_quality, warnings)
    assert verdict["edge_verdict"] == "VALIDATION_REQUIRED"
    assert verdict["confidence"] == "LOW"

