from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from quantlog.validate.validator import validate_path


class TestValidator(unittest.TestCase):
    def test_validate_path_reports_errors_for_missing_payload_field(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir)
            event_file = path / "events.jsonl"
            event = {
                "event_id": "00000000-0000-0000-0000-000000000011",
                "event_type": "trade_action",
                "event_version": 1,
                "timestamp_utc": "2026-03-29T18:00:03Z",
                "ingested_at_utc": "2026-03-29T18:00:03Z",
                "source_system": "quantbuild",
                "source_component": "decision_engine",
                "environment": "paper",
                "run_id": "run_test",
                "session_id": "session_test",
                "source_seq": 1,
                "trace_id": "trace_test",
                "severity": "info",
                "payload": {
                    "decision": "ENTER"
                    # missing required "reason"
                },
            }
            event_file.write_text(json.dumps(event) + "\n", encoding="utf-8")

            report = validate_path(path)
            error_messages = [issue.message for issue in report.issues if issue.level == "error"]

            self.assertEqual(report.files_scanned, 1)
            self.assertEqual(report.lines_scanned, 1)
            self.assertIn("missing_payload_field[trade_action]: reason", error_messages)

    def test_validate_path_accepts_valid_event(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir)
            event_file = path / "events.jsonl"
            event = {
                "event_id": "00000000-0000-0000-0000-000000000012",
                "event_type": "signal_evaluated",
                "event_version": 1,
                "timestamp_utc": "2026-03-29T18:00:00Z",
                "ingested_at_utc": "2026-03-29T18:00:01Z",
                "source_system": "quantbuild",
                "source_component": "signal_engine",
                "environment": "paper",
                "run_id": "run_test_ok",
                "session_id": "session_test_ok",
                "source_seq": 1,
                "trace_id": "trace_test_ok",
                "severity": "info",
                "payload": {
                    "signal_type": "ict_sweep",
                    "signal_direction": "LONG",
                    "confidence": 0.7,
                },
            }
            event_file.write_text(json.dumps(event) + "\n", encoding="utf-8")

            report = validate_path(path)
            self.assertEqual(report.events_valid, 1)
            self.assertEqual(len([issue for issue in report.issues if issue.level == "error"]), 0)

    def test_trade_action_decision_enum_is_enforced(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir)
            event_file = path / "events.jsonl"
            event = {
                "event_id": "00000000-0000-0000-0000-000000000013",
                "event_type": "trade_action",
                "event_version": 1,
                "timestamp_utc": "2026-03-29T18:00:03Z",
                "ingested_at_utc": "2026-03-29T18:00:03Z",
                "source_system": "quantbuild",
                "source_component": "decision_engine",
                "environment": "paper",
                "run_id": "run_test_sem",
                "session_id": "session_test_sem",
                "source_seq": 1,
                "trace_id": "trace_test_sem",
                "severity": "info",
                "payload": {"decision": "TRADE", "reason": "legacy_value_should_fail"},
            }
            event_file.write_text(json.dumps(event) + "\n", encoding="utf-8")

            report = validate_path(path)
            error_messages = [issue.message for issue in report.issues if issue.level == "error"]
            self.assertIn("invalid_trade_action_decision: TRADE", error_messages)


if __name__ == "__main__":
    unittest.main()

