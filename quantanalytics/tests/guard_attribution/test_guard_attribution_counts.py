from __future__ import annotations

from quantanalytics.guard_attribution.attribution import analyze_guards
from quantanalytics.guard_attribution.decision_cycles import reconstruct_decision_cycles


def test_guard_attribution_counts(sample_cycle_events):
    events = [dict(item) for item in sample_cycle_events]
    events[2] = dict(events[2], payload={"guard_name": "spread_guard", "guard_decision": "ALLOW"})
    cycles = reconstruct_decision_cycles(events)
    result = analyze_guards(cycles)

    row = result["guards"][0]
    assert row["guard_name"] == "spread_guard"
    assert row["allowed_count"] == 1
    assert row["blocked_count"] == 0

