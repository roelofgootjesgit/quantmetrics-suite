from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from quantlog.validate.validator import (
    ValidationIssue,
    aggregate_validation_issue_codes,
    validate_path,
    validation_issue_code,
)


class TestValidator(unittest.TestCase):
    def test_validation_issue_code_and_aggregate(self) -> None:
        self.assertEqual(
            validation_issue_code("missing_payload_field[trade_action]: reason"),
            "missing_payload_field[trade_action]",
        )
        self.assertEqual(validation_issue_code("invalid_run_id"), "invalid_run_id")
        path = Path("dummy.jsonl")
        issues = [
            ValidationIssue("error", path, 1, "invalid_run_id"),
            ValidationIssue("error", path, 2, "invalid_run_id"),
            ValidationIssue("warn", path, 3, "unknown_event_type: foo"),
        ]
        err_agg = aggregate_validation_issue_codes([i for i in issues if i.level == "error"])
        self.assertEqual(err_agg.get("invalid_run_id"), 2)

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

    def test_trade_action_no_action_reason_must_be_canonical(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir)
            event_file = path / "events.jsonl"
            event = {
                "event_id": "00000000-0000-0000-0000-000000000014",
                "event_type": "trade_action",
                "event_version": 1,
                "timestamp_utc": "2026-03-29T18:00:03Z",
                "ingested_at_utc": "2026-03-29T18:00:03Z",
                "source_system": "quantbuild",
                "source_component": "decision_engine",
                "environment": "paper",
                "run_id": "run_test_noact",
                "session_id": "session_test_noact",
                "source_seq": 1,
                "trace_id": "trace_test_noact",
                "severity": "info",
                "payload": {"decision": "NO_ACTION", "reason": "blocked_by_guard"},
            }
            event_file.write_text(json.dumps(event) + "\n", encoding="utf-8")

            report = validate_path(path)
            error_messages = [issue.message for issue in report.issues if issue.level == "error"]
            self.assertIn("invalid_no_action_reason: 'blocked_by_guard'", error_messages)

    def test_null_run_id_is_invalid(self) -> None:
        """JSON null for run_id must not pass (key present but empty)."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir)
            event_file = path / "events.jsonl"
            event = {
                "event_id": "00000000-0000-0000-0000-000000000015",
                "event_type": "trade_action",
                "event_version": 1,
                "timestamp_utc": "2026-03-29T18:00:03Z",
                "ingested_at_utc": "2026-03-29T18:00:03Z",
                "source_system": "quantbuild",
                "source_component": "decision_engine",
                "environment": "paper",
                "run_id": None,
                "session_id": "session_x",
                "source_seq": 1,
                "trace_id": "trace_x",
                "severity": "info",
                "payload": {"decision": "NO_ACTION", "reason": "no_setup"},
            }
            event_file.write_text(json.dumps(event) + "\n", encoding="utf-8")

            report = validate_path(path)
            error_messages = [issue.message for issue in report.issues if issue.level == "error"]
            self.assertIn("invalid_run_id", error_messages)

    def test_source_seq_must_be_strictly_increasing_per_component_stream(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir)
            event_file = path / "events.jsonl"
            base = {
                "event_version": 1,
                "timestamp_utc": "2026-03-29T18:00:03Z",
                "ingested_at_utc": "2026-03-29T18:00:03Z",
                "source_system": "quantbuild",
                "source_component": "decision_engine",
                "environment": "paper",
                "run_id": "run_mono",
                "session_id": "session_mono",
                "trace_id": "trace_mono",
                "severity": "info",
            }
            e1 = {
                **base,
                "event_id": "00000000-0000-0000-0000-000000000016",
                "event_type": "trade_action",
                "source_seq": 1,
                "payload": {"decision": "NO_ACTION", "reason": "no_setup"},
            }
            e2 = {
                **base,
                "event_id": "00000000-0000-0000-0000-000000000017",
                "event_type": "trade_action",
                "source_seq": 1,
                "payload": {"decision": "NO_ACTION", "reason": "cooldown_active"},
            }
            event_file.write_text(
                "\n".join([json.dumps(e1), json.dumps(e2)]) + "\n", encoding="utf-8"
            )

            report = validate_path(path)
            error_messages = [issue.message for issue in report.issues if issue.level == "error"]
            self.assertTrue(any(m.startswith("source_seq_not_monotonic:") for m in error_messages))
            self.assertEqual(report.events_valid, 1)


if __name__ == "__main__":
    unittest.main()

