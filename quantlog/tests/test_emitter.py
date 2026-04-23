from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from quantlog.ingest.adapters import QuantBuildEmitter
from quantlog.replay.service import replay_trace


class TestEmitter(unittest.TestCase):
    def test_emitter_assigns_incremental_source_seq(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            base_path = Path(tmp_dir)
            emitter = QuantBuildEmitter.from_base_path(
                base_path=base_path,
                environment="paper",
                run_id="run_emitter_test",
                session_id="session_emitter_test",
            )

            emitter.emit(
                event_type="signal_evaluated",
                trace_id="trace_seq",
                decision_cycle_id="dc_emit_seq",
                payload={
                    "signal_type": "ict_sweep",
                    "signal_direction": "LONG",
                    "confidence": 0.6,
                },
            )
            emitter.emit(
                event_type="trade_action",
                trace_id="trace_seq",
                decision_cycle_id="dc_emit_seq",
                payload={
                    "decision": "ENTER",
                    "reason": "ok",
                    "trade_id": "trade_emit_seq_1",
                },
            )

            replay_items = replay_trace(base_path, "trace_seq")
            self.assertEqual(len(replay_items), 2)
            self.assertEqual(replay_items[0].source_seq, 1)
            self.assertEqual(replay_items[1].source_seq, 2)


if __name__ == "__main__":
    unittest.main()

