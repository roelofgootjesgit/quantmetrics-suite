from __future__ import annotations

from pathlib import Path

from quantanalytics.guard_attribution.loader import load_events


def test_quantanalytics_loads_demo_jsonl() -> None:
    demo_file = Path(__file__).resolve().parents[1] / "examples" / "demo_quantlog_events.jsonl"
    events = load_events(str(demo_file))
    assert len(events) == 6
    assert events[0]["event_type"] == "signal_detected"

    metadata = getattr(load_events, "last_metadata", {})
    assert metadata["total_events"] == 6
    assert metadata["event_type_counts"]["trade_closed"] == 1
