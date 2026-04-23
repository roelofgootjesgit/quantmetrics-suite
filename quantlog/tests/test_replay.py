from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from quantlog.replay.service import replay_trace


class TestReplay(unittest.TestCase):
    def test_replay_trace_returns_sorted_timeline(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir)
            events_file = path / "events.jsonl"

            first = {
                "event_id": "00000000-0000-0000-0000-000000000021",
                "event_type": "trade_action",
                "event_version": 1,
                "timestamp_utc": "2026-03-29T18:00:03Z",
                "ingested_at_utc": "2026-03-29T18:00:03Z",
                "source_system": "quantbuild",
                "source_component": "decision_engine",
                "environment": "paper",
                "run_id": "run_replay_test",
                "session_id": "session_replay_test",
                "source_seq": 2,
                "trace_id": "trace_replay_test",
                "decision_cycle_id": "dc_replay_test",
                "severity": "info",
                "payload": {
                    "decision": "ENTER",
                    "reason": "ok",
                    "trade_id": "trade_replay_1",
                },
            }
            second = {
                "event_id": "00000000-0000-0000-0000-000000000022",
                "event_type": "signal_evaluated",
                "event_version": 1,
                "timestamp_utc": "2026-03-29T18:00:03Z",
                "ingested_at_utc": "2026-03-29T18:00:01Z",
                "source_system": "quantbuild",
                "source_component": "signal_engine",
                "environment": "paper",
                "run_id": "run_replay_test",
                "session_id": "session_replay_test",
                "source_seq": 1,
                "trace_id": "trace_replay_test",
                "decision_cycle_id": "dc_replay_test",
                "severity": "info",
                "payload": {
                    "signal_type": "ict_sweep",
                    "signal_direction": "LONG",
                    "confidence": 0.6,
                },
            }

            events_file.write_text(
                "\n".join([json.dumps(first), json.dumps(second)]) + "\n",
                encoding="utf-8",
            )

            timeline = replay_trace(path, trace_id="trace_replay_test")
            self.assertEqual(len(timeline), 2)
            self.assertEqual(timeline[0].event_type, "signal_evaluated")
            self.assertEqual(timeline[1].event_type, "trade_action")


if __name__ == "__main__":
    unittest.main()

