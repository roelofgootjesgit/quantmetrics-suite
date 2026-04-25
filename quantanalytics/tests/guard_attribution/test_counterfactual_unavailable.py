from __future__ import annotations

from quantanalytics.guard_attribution.attribution import analyze_guards
from quantanalytics.guard_attribution.decision_cycles import reconstruct_decision_cycles


def test_counterfactual_unavailable(sample_cycle_events):
    events = [dict(item) for item in sample_cycle_events]
    events[2] = dict(events[2], payload={"guard_name": "news_guard", "guard_decision": "BLOCK"})
    events = [event for event in events if event["event_type"] != "trade_closed"]
    cycles = reconstruct_decision_cycles(events)

    result = analyze_guards(cycles)
    row = result["guards"][0]
    assert row["blocked_count"] == 1
    assert row["counterfactual_available"] is False
    assert row["reason"] == "No shadow outcome available for blocked signals"

