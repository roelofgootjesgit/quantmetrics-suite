from __future__ import annotations

from quantanalytics.guard_attribution.decision_cycles import reconstruct_decision_cycles
from quantanalytics.guard_attribution.throughput import analyze_throughput


def test_throughput_diagnostics(sample_cycle_events):
    events = [dict(item) for item in sample_cycle_events]
    events.append(
        {
            "event_type": "signal_detected",
            "timestamp_utc": "2026-04-25T04:21:35Z",
            "run_id": "r1",
            "decision_cycle_id": "noise",
            "payload": {},
        }
    )

    cycles = reconstruct_decision_cycles(events)
    throughput = analyze_throughput(events, cycles)

    assert throughput["raw_signals_detected"] == 2
    assert throughput["signals_executed"] == 1
    assert throughput["signals_after_filters"] == 1
    assert throughput["filter_kill_ratio"] == 0.5
    assert throughput["execution_ratio"] == 0.5
