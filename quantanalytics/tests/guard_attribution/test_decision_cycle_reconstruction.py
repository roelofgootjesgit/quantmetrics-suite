from __future__ import annotations

from quantanalytics.guard_attribution.decision_cycles import reconstruct_decision_cycles


def test_decision_cycle_reconstruction(sample_cycle_events):
    cycles = reconstruct_decision_cycles(sample_cycle_events)

    assert len(cycles) == 1
    cycle = cycles[0]
    assert cycle.decision_cycle_id == "dc-1"
    assert cycle.trade_closed is not None
    assert cycle.pnl_r == 1.2
    assert cycle.incomplete is False

