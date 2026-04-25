from __future__ import annotations

from quantanalytics.guard_attribution.decision_cycles import reconstruct_decision_cycles
from quantanalytics.guard_attribution.stability import analyze_stability


def test_edge_stability_low_sample(sample_cycle_events):
    cycles = reconstruct_decision_cycles(sample_cycle_events)
    stability = analyze_stability(cycles)

    regime_row = stability["regime"][0]
    assert regime_row["trade_count"] == 1
    assert regime_row["sample_quality"] == "INSUFFICIENT_DATA"
    assert regime_row["verdict"] == "PROMISING_BUT_WEAK"

