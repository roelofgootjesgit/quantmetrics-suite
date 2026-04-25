from __future__ import annotations

from quantanalytics.guard_attribution.decision_cycles import reconstruct_decision_cycles


def test_missing_decision_cycle_id_warning(sample_cycle_events):
    events = [dict(item) for item in sample_cycle_events]
    events[0]["decision_cycle_id"] = None

    reconstruct_decision_cycles(events)
    metadata = getattr(reconstruct_decision_cycles, "last_metadata")

    assert metadata["warning_counts"]["DECISION_CYCLE_ID_MISSING"] >= 1

