from __future__ import annotations

from quantanalytics.guard_attribution.decision_cycles import reconstruct_decision_cycles
from quantanalytics.guard_attribution.scoring import score_decision_cycles


def test_decision_quality_scoring(sample_cycle_events):
    cycles = reconstruct_decision_cycles(sample_cycle_events)
    rows = score_decision_cycles(cycles)

    assert len(rows) == 1
    assert rows[0]["quality_score"] >= 2
    assert rows[0]["quality_label"] == "HIGH_QUALITY"

