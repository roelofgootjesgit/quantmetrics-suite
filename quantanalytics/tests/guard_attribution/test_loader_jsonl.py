from __future__ import annotations

import json

from quantanalytics.guard_attribution.loader import load_events


def test_loader_jsonl_reads_events(tmp_path):
    path = tmp_path / "events.jsonl"
    payload = [
        {"event_type": "signal_detected", "timestamp_utc": "2026-01-01T00:00:00Z", "run_id": "r1", "decision_cycle_id": "dc1", "payload": {}},
        {"event_type": "trade_action", "timestamp_utc": "2026-01-01T00:00:01Z", "run_id": "r1", "decision_cycle_id": "dc1", "payload": {"action": "ENTER"}},
    ]
    path.write_text("\n".join(json.dumps(row) for row in payload) + "\n", encoding="utf-8")

    events = load_events(str(path))

    assert len(events) == 2
    meta = getattr(load_events, "last_metadata")
    assert meta["total_events"] == 2
    assert meta["event_type_counts"]["signal_detected"] == 1

