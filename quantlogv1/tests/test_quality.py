from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from quantlog.ingest.adapters import QuantBuildEmitter
from quantlog.quality.service import score_run
from quantlog.events.io import discover_jsonl_files


class TestQuality(unittest.TestCase):
    def test_score_run_passes_for_clean_dataset(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            qb = QuantBuildEmitter.from_base_path(
                base_path=root,
                environment="paper",
                run_id="run_quality_test",
                session_id="session_quality_test",
            )
            qb.emit(
                event_type="signal_evaluated",
                trace_id="trace_quality_1",
                timestamp_utc="2026-03-29T18:00:00Z",
                decision_cycle_id="dc_quality_1",
                payload={
                    "signal_type": "ict_sweep",
                    "signal_direction": "LONG",
                    "confidence": 0.7,
                },
            )
            qb.emit(
                event_type="risk_guard_decision",
                trace_id="trace_quality_1",
                timestamp_utc="2026-03-29T18:00:01Z",
                decision_cycle_id="dc_quality_1",
                payload={"guard_name": "spread_guard", "decision": "BLOCK", "reason": "spread"},
            )
            qb.emit(
                event_type="trade_action",
                trace_id="trace_quality_1",
                timestamp_utc="2026-03-29T18:00:02Z",
                decision_cycle_id="dc_quality_1",
                payload={"decision": "NO_ACTION", "reason": "risk_blocked"},
            )

            report = score_run(root, max_gap_seconds=300, pass_threshold=95)
            self.assertTrue(report.passed)
            self.assertGreaterEqual(report.score, 95)
            self.assertEqual(report.errors_total, 0)
            self.assertEqual(report.duplicate_event_ids, 0)
            self.assertEqual(report.trades_attempted, 0)
            self.assertEqual(report.blocks_total, 1)
            self.assertEqual(report.trade_action_by_decision.get("NO_ACTION"), 1)
            self.assertEqual(report.no_action_by_reason.get("risk_blocked"), 1)
            self.assertEqual(report.risk_guard_blocks_by_guard.get("spread_guard"), 1)
            self.assertEqual(report.risk_guard_by_decision.get("BLOCK"), 1)
            self.assertEqual(report.by_event_type.get("signal_evaluated"), 1)
            self.assertEqual(report.by_event_type.get("trade_action"), 1)
            self.assertEqual(report.by_severity.get("info"), 3)
            self.assertEqual(report.by_source_system.get("quantbuild"), 3)
            self.assertEqual(report.by_environment.get("paper"), 3)
            self.assertEqual(report.by_source_component.get("quantbuild_adapter"), 3)
            self.assertEqual(report.non_contract_event_types, {})
            self.assertEqual(report.count_unique_run_ids, 1)
            self.assertEqual(report.count_unique_session_ids, 1)
            self.assertEqual(report.count_unique_trace_ids, 1)

    def test_score_run_fails_when_anomalies_are_present(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            generated_root = root / "generated"
            date = "2026-03-29"

            import subprocess
            import sys

            cmd = [
                sys.executable,
                "scripts/generate_sample_day.py",
                "--output-path",
                str(generated_root),
                "--date",
                date,
                "--traces",
                "15",
                "--inject-anomalies",
            ]
            completed = subprocess.run(cmd, check=False)
            self.assertEqual(completed.returncode, 0)

            day_path = generated_root / date
            self.assertTrue(len(discover_jsonl_files(day_path)) > 0)
            report = score_run(day_path, max_gap_seconds=300, pass_threshold=95)
            self.assertFalse(report.passed)
            self.assertGreater(report.duplicate_event_ids, 0)
            self.assertGreater(report.missing_trace_ids, 0)


if __name__ == "__main__":
    unittest.main()

