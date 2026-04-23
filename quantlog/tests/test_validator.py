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
                "decision_cycle_id": "dc_missing_reason",
                "severity": "info",
                "payload": {
                    "decision": "ENTER",
                    "trade_id": "trade_missing_reason",
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
            ev_signal = {
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
                "decision_cycle_id": "dc_ok_signal_evaluated",
                "severity": "info",
                "payload": {
                    "signal_type": "ict_sweep",
                    "signal_direction": "LONG",
                    "confidence": 0.7,
                },
            }
            ev_terminal = {
                "event_id": "00000000-0000-0000-0000-000000000013",
                "event_type": "trade_action",
                "event_version": 1,
                "timestamp_utc": "2026-03-29T18:00:05Z",
                "ingested_at_utc": "2026-03-29T18:00:05Z",
                "source_system": "quantbuild",
                "source_component": "decision_engine",
                "environment": "paper",
                "run_id": "run_test_ok",
                "session_id": "session_test_ok",
                "source_seq": 1,
                "trace_id": "trace_test_ok",
                "decision_cycle_id": "dc_ok_signal_evaluated",
                "severity": "info",
                "payload": {"decision": "NO_ACTION", "reason": "no_setup"},
            }
            event_file.write_text(
                json.dumps(ev_signal) + "\n" + json.dumps(ev_terminal) + "\n", encoding="utf-8"
            )

            report = validate_path(path)
            self.assertEqual(report.events_valid, 2)
            self.assertEqual(len([issue for issue in report.issues if issue.level == "error"]), 0)

    def test_quantbuild_chain_requires_decision_cycle_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir)
            event_file = path / "events.jsonl"
            event = {
                "event_id": "00000000-0000-0000-0000-000000000099",
                "event_type": "signal_evaluated",
                "event_version": 1,
                "timestamp_utc": "2026-03-29T18:00:00Z",
                "ingested_at_utc": "2026-03-29T18:00:01Z",
                "source_system": "quantbuild",
                "source_component": "signal_engine",
                "environment": "paper",
                "run_id": "run_dc",
                "session_id": "session_dc",
                "source_seq": 1,
                "trace_id": "trace_dc",
                "severity": "info",
                "payload": {
                    "signal_type": "ict_sweep",
                    "signal_direction": "LONG",
                    "confidence": 0.7,
                },
            }
            event_file.write_text(json.dumps(event) + "\n", encoding="utf-8")

            report = validate_path(path)
            error_messages = [issue.message for issue in report.issues if issue.level == "error"]
            self.assertIn("missing_decision_cycle_id_quantbuild_chain", error_messages)

    def test_trade_action_enter_requires_trade_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir)
            event_file = path / "events.jsonl"
            event = {
                "event_id": "00000000-0000-0000-0000-000000000098",
                "event_type": "trade_action",
                "event_version": 1,
                "timestamp_utc": "2026-03-29T18:00:03Z",
                "ingested_at_utc": "2026-03-29T18:00:03Z",
                "source_system": "quantbuild",
                "source_component": "decision_engine",
                "environment": "paper",
                "run_id": "run_tid",
                "session_id": "session_tid",
                "source_seq": 1,
                "trace_id": "trace_tid",
                "decision_cycle_id": "dc_enter_tid",
                "severity": "info",
                "payload": {"decision": "ENTER", "reason": "ok"},
            }
            event_file.write_text(json.dumps(event) + "\n", encoding="utf-8")

            report = validate_path(path)
            error_messages = [issue.message for issue in report.issues if issue.level == "error"]
            self.assertIn("trade_action_enter_missing_trade_id", error_messages)

    def test_signal_evaluated_desk_grade_optional_payload_valid(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir)
            event_file = path / "events.jsonl"
            ev_signal = {
                "event_id": "00000000-0000-0000-0000-000000000022",
                "event_type": "signal_evaluated",
                "event_version": 1,
                "timestamp_utc": "2026-03-29T18:00:00Z",
                "ingested_at_utc": "2026-03-29T18:00:01Z",
                "source_system": "quantbuild",
                "source_component": "signal_engine",
                "environment": "paper",
                "run_id": "run_upgrade",
                "session_id": "session_upgrade",
                "source_seq": 1,
                "trace_id": "trace_upgrade",
                "decision_cycle_id": "dc_upgrade_desk_grade",
                "severity": "info",
                "payload": {
                    "signal_type": "ict_sweep",
                    "signal_direction": "NONE",
                    "confidence": 0.0,
                    "new_bar_detected": False,
                    "bar_ts": "2026-04-17T14:30:00Z",
                    "poll_ts": "2026-04-17T14:31:25Z",
                    "same_bar_guard_triggered": True,
                    "same_bar_guard_reason": "last_processed_bar_ts_matches_latest_bar_ts",
                    "same_bar_skip_count_for_bar": 3,
                    "gate_summary": {
                        "session_gate": "pass",
                        "regime_gate": "pass",
                        "structure_gate": "fail",
                        "liquidity_gate": "fail",
                        "trigger_gate": "fail",
                        "same_bar_guard": "pass",
                        "risk_gate": "not_reached",
                    },
                    "blocked_by_primary_gate": "structure_gate",
                    "blocked_by_secondary_gate": "trigger_gate",
                    "evaluation_path": ["session_gate", "regime_gate", "structure_gate"],
                    "near_entry_score": 0.35,
                    "closest_to_entry_side": "long",
                    "combo_active_modules_count_long": 1,
                    "combo_active_modules_count_short": 0,
                    "missing_modules_long": ["trigger", "liquidity"],
                    "missing_modules_short": ["structure", "liquidity", "trigger"],
                    "entry_distance_long": 2,
                    "entry_distance_short": 3,
                    "modules_long": {"structure": True, "liquidity": False, "trigger": False},
                    "modules_short": {"structure": False, "liquidity": False, "trigger": False},
                    "setup_candidate": False,
                    "candidate_strength": 0.22,
                    "entry_ready": False,
                    "threshold_snapshot": {"min_combo_required": 3},
                },
            }
            ev_terminal = {
                "event_id": "00000000-0000-0000-0000-000000000024",
                "event_type": "trade_action",
                "event_version": 1,
                "timestamp_utc": "2026-03-29T18:00:05Z",
                "ingested_at_utc": "2026-03-29T18:00:05Z",
                "source_system": "quantbuild",
                "source_component": "decision_engine",
                "environment": "paper",
                "run_id": "run_upgrade",
                "session_id": "session_upgrade",
                "source_seq": 1,
                "trace_id": "trace_upgrade",
                "decision_cycle_id": "dc_upgrade_desk_grade",
                "severity": "info",
                "payload": {"decision": "NO_ACTION", "reason": "no_setup"},
            }
            event_file.write_text(
                json.dumps(ev_signal) + "\n" + json.dumps(ev_terminal) + "\n", encoding="utf-8"
            )
            report = validate_path(path)
            self.assertEqual(report.events_valid, 2)
            self.assertEqual(len([i for i in report.issues if i.level == "error"]), 0)

    def test_signal_evaluated_invalid_gate_summary_status_errors(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir)
            event_file = path / "events.jsonl"
            event = {
                "event_id": "00000000-0000-0000-0000-000000000023",
                "event_type": "signal_evaluated",
                "event_version": 1,
                "timestamp_utc": "2026-03-29T18:00:00Z",
                "ingested_at_utc": "2026-03-29T18:00:01Z",
                "source_system": "quantbuild",
                "source_component": "signal_engine",
                "environment": "paper",
                "run_id": "run_bad_gs",
                "session_id": "session_bad_gs",
                "source_seq": 1,
                "trace_id": "trace_bad_gs",
                "decision_cycle_id": "dc_bad_gs",
                "severity": "info",
                "payload": {
                    "signal_type": "ict_sweep",
                    "signal_direction": "LONG",
                    "confidence": 0.5,
                    "gate_summary": {"session_gate": "blocked"},
                },
            }
            event_file.write_text(json.dumps(event) + "\n", encoding="utf-8")
            report = validate_path(path)
            self.assertEqual(report.events_valid, 0)
            error_messages = [issue.message for issue in report.issues if issue.level == "error"]
            self.assertTrue(
                any(m.startswith("signal_evaluated_invalid_gate_summary_status") for m in error_messages)
            )

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
                "decision_cycle_id": "dc_enum_sem",
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
                "decision_cycle_id": "dc_no_act_canonical",
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
                "decision_cycle_id": "dc_null_run_id",
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
                "decision_cycle_id": "dc_seq_mono",
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
                "decision_cycle_id": "dc_seq_mono_2",
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

    def test_signal_detected_valid_minimal_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir)
            event_file = path / "events.jsonl"
            ev_sd = {
                "event_id": "00000000-0000-0000-0000-000000000018",
                "event_type": "signal_detected",
                "event_version": 1,
                "timestamp_utc": "2026-03-29T18:00:00Z",
                "ingested_at_utc": "2026-03-29T18:00:01Z",
                "source_system": "quantbuild",
                "source_component": "live_runner",
                "environment": "paper",
                "run_id": "run_sd",
                "session_id": "session_sd",
                "source_seq": 1,
                "trace_id": "trace_sd",
                "decision_cycle_id": "dc_signal_detected_min",
                "severity": "info",
                "payload": {
                    "signal_id": "sig_1",
                    "type": "sqe_entry",
                    "direction": "LONG",
                    "strength": 1.0,
                    "bar_timestamp": "2026-03-29T17:45:00Z",
                    "session": "London",
                    "regime": "trend",
                },
            }
            ev_terminal = {
                "event_id": "00000000-0000-0000-0000-000000000029",
                "event_type": "trade_action",
                "event_version": 1,
                "timestamp_utc": "2026-03-29T18:00:05Z",
                "ingested_at_utc": "2026-03-29T18:00:05Z",
                "source_system": "quantbuild",
                "source_component": "decision_engine",
                "environment": "paper",
                "run_id": "run_sd",
                "session_id": "session_sd",
                "source_seq": 1,
                "trace_id": "trace_sd",
                "decision_cycle_id": "dc_signal_detected_min",
                "severity": "info",
                "payload": {"decision": "NO_ACTION", "reason": "no_setup"},
            }
            event_file.write_text(
                json.dumps(ev_sd) + "\n" + json.dumps(ev_terminal) + "\n", encoding="utf-8"
            )
            report = validate_path(path)
            self.assertEqual(report.events_valid, 2)
            self.assertEqual(len([i for i in report.issues if i.level == "error"]), 0)

    def test_signal_filtered_reason_must_be_canonical(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir)
            event_file = path / "events.jsonl"
            event = {
                "event_id": "00000000-0000-0000-0000-000000000019",
                "event_type": "signal_filtered",
                "event_version": 1,
                "timestamp_utc": "2026-03-29T18:00:00Z",
                "ingested_at_utc": "2026-03-29T18:00:01Z",
                "source_system": "quantbuild",
                "source_component": "live_runner",
                "environment": "paper",
                "run_id": "run_sf",
                "session_id": "session_sf",
                "source_seq": 1,
                "trace_id": "trace_sf",
                "severity": "info",
                "payload": {
                    "filter_reason": "not_a_canonical_reason",
                    "raw_reason": "foo",
                },
            }
            event_file.write_text(json.dumps(event) + "\n", encoding="utf-8")
            report = validate_path(path)
            error_messages = [issue.message for issue in report.issues if issue.level == "error"]
            self.assertIn("invalid_signal_filtered_reason: 'not_a_canonical_reason'", error_messages)

    def test_trade_executed_direction_enum(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir)
            event_file = path / "events.jsonl"
            event = {
                "event_id": "00000000-0000-0000-0000-000000000020",
                "event_type": "trade_executed",
                "event_version": 1,
                "timestamp_utc": "2026-03-29T18:00:00Z",
                "ingested_at_utc": "2026-03-29T18:00:01Z",
                "source_system": "quantbuild",
                "source_component": "live_runner",
                "environment": "paper",
                "run_id": "run_te",
                "session_id": "session_te",
                "source_seq": 1,
                "trace_id": "trace_te",
                "severity": "info",
                "order_ref": "ord_1",
                "payload": {"direction": "BUY", "trade_id": "t1"},
            }
            event_file.write_text(json.dumps(event) + "\n", encoding="utf-8")
            report = validate_path(path)
            error_messages = [issue.message for issue in report.issues if issue.level == "error"]
            self.assertIn("invalid_trade_executed_direction: BUY", error_messages)

    def test_decision_cycle_requires_terminal_trade_action(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir)
            event_file = path / "events.jsonl"
            ev = {
                "event_id": "00000000-0000-0000-0000-000000000071",
                "event_type": "signal_evaluated",
                "event_version": 1,
                "timestamp_utc": "2026-03-29T18:00:00Z",
                "ingested_at_utc": "2026-03-29T18:00:01Z",
                "source_system": "quantbuild",
                "source_component": "signal_engine",
                "environment": "paper",
                "run_id": "run_miss_ta",
                "session_id": "session_miss_ta",
                "source_seq": 1,
                "trace_id": "trace_miss_ta",
                "decision_cycle_id": "dc_missing_terminal",
                "severity": "info",
                "payload": {
                    "signal_type": "ict_sweep",
                    "signal_direction": "LONG",
                    "confidence": 0.5,
                },
            }
            event_file.write_text(json.dumps(ev) + "\n", encoding="utf-8")
            report = validate_path(path)
            msgs = [i.message for i in report.issues if i.level == "error"]
            self.assertTrue(any(m.startswith("decision_cycle_missing_trade_action") for m in msgs))

    def test_decision_cycle_rejects_duplicate_trade_action(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir)
            event_file = path / "events.jsonl"
            base = {
                "event_version": 1,
                "timestamp_utc": "2026-03-29T18:00:03Z",
                "ingested_at_utc": "2026-03-29T18:00:03Z",
                "source_system": "quantbuild",
                "environment": "paper",
                "run_id": "run_dup_ta",
                "session_id": "session_dup_ta",
                "trace_id": "trace_dup_ta",
                "decision_cycle_id": "dc_dup_trade_action",
                "severity": "info",
            }
            a = {
                **base,
                "event_id": "00000000-0000-0000-0000-000000000081",
                "event_type": "trade_action",
                "source_component": "decision_engine",
                "source_seq": 1,
                "payload": {"decision": "NO_ACTION", "reason": "no_setup"},
            }
            b = {
                **base,
                "event_id": "00000000-0000-0000-0000-000000000082",
                "event_type": "trade_action",
                "source_component": "decision_engine",
                "source_seq": 2,
                "payload": {"decision": "NO_ACTION", "reason": "cooldown_active"},
            }
            event_file.write_text(json.dumps(a) + "\n" + json.dumps(b) + "\n", encoding="utf-8")
            report = validate_path(path)
            msgs = [i.message for i in report.issues if i.level == "error"]
            self.assertTrue(any(m.startswith("duplicate_trade_action_decision_cycle") for m in msgs))

    def test_decision_cycle_trace_id_must_match_across_chain(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir)
            f = path / "events.jsonl"
            se = {
                "event_id": "00000000-0000-0000-0000-000000000111",
                "event_type": "signal_evaluated",
                "event_version": 1,
                "timestamp_utc": "2026-03-29T18:00:00Z",
                "ingested_at_utc": "2026-03-29T18:00:01Z",
                "source_system": "quantbuild",
                "source_component": "signal_engine",
                "environment": "paper",
                "run_id": "run_tr",
                "session_id": "session_tr",
                "source_seq": 1,
                "trace_id": "trace_a",
                "decision_cycle_id": "dc_trace_enforce",
                "severity": "info",
                "payload": {
                    "signal_type": "ict_sweep",
                    "signal_direction": "LONG",
                    "confidence": 0.5,
                },
            }
            ta = {
                "event_id": "00000000-0000-0000-0000-000000000112",
                "event_type": "trade_action",
                "event_version": 1,
                "timestamp_utc": "2026-03-29T18:00:05Z",
                "ingested_at_utc": "2026-03-29T18:00:05Z",
                "source_system": "quantbuild",
                "source_component": "decision_engine",
                "environment": "paper",
                "run_id": "run_tr",
                "session_id": "session_tr",
                "source_seq": 1,
                "trace_id": "trace_b",
                "decision_cycle_id": "dc_trace_enforce",
                "severity": "info",
                "payload": {
                    "decision": "NO_ACTION",
                    "reason": "no_setup",
                },
            }
            f.write_text(json.dumps(se) + "\n" + json.dumps(ta) + "\n", encoding="utf-8")
            report = validate_path(path)
            msgs = [i.message for i in report.issues if i.level == "error"]
            self.assertTrue(any(m.startswith("decision_cycle_trace_id_mismatch") for m in msgs))

    def test_decision_cycle_symbol_mismatch_errors(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir)
            f = path / "events.jsonl"
            se = {
                "event_id": "00000000-0000-0000-0000-000000000121",
                "event_type": "signal_evaluated",
                "event_version": 1,
                "timestamp_utc": "2026-03-29T18:00:00Z",
                "ingested_at_utc": "2026-03-29T18:00:01Z",
                "source_system": "quantbuild",
                "source_component": "signal_engine",
                "environment": "paper",
                "run_id": "run_sym",
                "session_id": "session_sym",
                "source_seq": 1,
                "trace_id": "trace_sym",
                "symbol": "XAUUSD",
                "decision_cycle_id": "dc_sym_enforce",
                "severity": "info",
                "payload": {
                    "signal_type": "ict_sweep",
                    "signal_direction": "LONG",
                    "confidence": 0.5,
                },
            }
            ta = {
                "event_id": "00000000-0000-0000-0000-000000000122",
                "event_type": "trade_action",
                "event_version": 1,
                "timestamp_utc": "2026-03-29T18:00:05Z",
                "ingested_at_utc": "2026-03-29T18:00:05Z",
                "source_system": "quantbuild",
                "source_component": "decision_engine",
                "environment": "paper",
                "run_id": "run_sym",
                "session_id": "session_sym",
                "source_seq": 1,
                "trace_id": "trace_sym",
                "symbol": "EURUSD",
                "decision_cycle_id": "dc_sym_enforce",
                "severity": "info",
                "payload": {"decision": "NO_ACTION", "reason": "no_setup"},
            }
            f.write_text(json.dumps(se) + "\n" + json.dumps(ta) + "\n", encoding="utf-8")
            report = validate_path(path)
            msgs = [i.message for i in report.issues if i.level == "error"]
            self.assertTrue(any(m.startswith("decision_cycle_symbol_mismatch") for m in msgs))

    def test_decision_chain_order_trade_action_must_follow_signal_evaluated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir)
            event_file = path / "events.jsonl"
            ta_first = {
                "event_id": "00000000-0000-0000-0000-000000000091",
                "event_type": "trade_action",
                "event_version": 1,
                "timestamp_utc": "2026-03-29T18:00:01Z",
                "ingested_at_utc": "2026-03-29T18:00:01Z",
                "source_system": "quantbuild",
                "source_component": "decision_engine",
                "environment": "paper",
                "run_id": "run_ord",
                "session_id": "session_ord",
                "source_seq": 1,
                "trace_id": "trace_ord",
                "decision_cycle_id": "dc_bad_order",
                "severity": "info",
                "payload": {"decision": "NO_ACTION", "reason": "no_setup"},
            }
            se_second = {
                "event_id": "00000000-0000-0000-0000-000000000092",
                "event_type": "signal_evaluated",
                "event_version": 1,
                "timestamp_utc": "2026-03-29T18:00:05Z",
                "ingested_at_utc": "2026-03-29T18:00:05Z",
                "source_system": "quantbuild",
                "source_component": "signal_engine",
                "environment": "paper",
                "run_id": "run_ord",
                "session_id": "session_ord",
                "source_seq": 1,
                "trace_id": "trace_ord",
                "decision_cycle_id": "dc_bad_order",
                "severity": "info",
                "payload": {
                    "signal_type": "ict_sweep",
                    "signal_direction": "LONG",
                    "confidence": 0.5,
                },
            }
            event_file.write_text(
                json.dumps(ta_first) + "\n" + json.dumps(se_second) + "\n", encoding="utf-8"
            )
            report = validate_path(path)
            msgs = [i.message for i in report.issues if i.level == "error"]
            self.assertTrue(any(m.startswith("decision_chain_order_violation") for m in msgs))

    def test_trade_id_correlation_must_match_run_session_trace(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir)
            f = path / "events.jsonl"
            blk = {
                "event_version": 1,
                "timestamp_utc": "2026-03-29T18:00:00Z",
                "ingested_at_utc": "2026-03-29T18:00:01Z",
                "source_system": "quantbridge",
                "source_component": "exec",
                "environment": "paper",
                "session_id": "session_same",
                "severity": "info",
                "trade_id": "trade_dup_ref",
                "trace_id": "trace_one",
            }
            a = {
                **blk,
                "event_id": "00000000-0000-0000-0000-000000000101",
                "event_type": "order_submitted",
                "run_id": "run_one",
                "source_seq": 1,
                "payload": {
                    "order_ref": "o1",
                    "side": "BUY",
                    "volume": 1.0,
                    "trade_id": "trade_dup_ref",
                },
            }
            b = {
                **blk,
                "event_id": "00000000-0000-0000-0000-000000000102",
                "event_type": "order_filled",
                "run_id": "run_two",
                "source_seq": 1,
                "payload": {"order_ref": "o1", "fill_price": 1.0, "trade_id": "trade_dup_ref"},
            }
            f.write_text(json.dumps(a) + "\n" + json.dumps(b) + "\n", encoding="utf-8")
            report = validate_path(path)
            msgs = [i.message for i in report.issues if i.level == "error"]
            self.assertTrue(any(m.startswith("trade_id_correlation_mismatch") for m in msgs))

    def test_order_ref_trade_id_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir)
            f = path / "e.jsonl"
            base = {
                "event_version": 1,
                "timestamp_utc": "2026-03-29T18:00:00Z",
                "ingested_at_utc": "2026-03-29T18:00:01Z",
                "source_system": "quantbridge",
                "source_component": "exec",
                "environment": "paper",
                "run_id": "run_r",
                "session_id": "session_r",
                "trace_id": "trace_r",
                "severity": "info",
            }
            a = {
                **base,
                "event_id": "00000000-0000-0000-0000-000000000201",
                "event_type": "order_submitted",
                "order_ref": "ord_m",
                "trade_id": "t1",
                "source_seq": 1,
                "payload": {"order_ref": "ord_m", "side": "BUY", "volume": 1.0, "trade_id": "t1"},
            }
            b = {
                **base,
                "event_id": "00000000-0000-0000-0000-000000000202",
                "event_type": "order_filled",
                "order_ref": "ord_m",
                "trade_id": "t2",
                "source_seq": 2,
                "payload": {"order_ref": "ord_m", "fill_price": 1.0, "trade_id": "t2"},
            }
            f.write_text(json.dumps(a) + "\n" + json.dumps(b) + "\n", encoding="utf-8")
            report = validate_path(path)
            msgs = [i.message for i in report.issues if i.level == "error"]
            self.assertTrue(any(m.startswith("order_ref_trade_id_mismatch") for m in msgs))

    def test_decision_cycle_trade_id_linkage_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir)
            f = path / "e.jsonl"
            dc = "dc_linkage_fail"
            enter = {
                "event_id": "00000000-0000-0000-0000-000000000301",
                "event_type": "trade_action",
                "event_version": 1,
                "timestamp_utc": "2026-03-29T18:00:00Z",
                "ingested_at_utc": "2026-03-29T18:00:01Z",
                "source_system": "quantbuild",
                "source_component": "decision_engine",
                "environment": "paper",
                "run_id": "run_lk",
                "session_id": "session_lk",
                "source_seq": 1,
                "trace_id": "trace_lk",
                "decision_cycle_id": dc,
                "symbol": "XAUUSD",
                "severity": "info",
                "payload": {
                    "decision": "ENTER",
                    "reason": "ok",
                    "side": "BUY",
                    "trade_id": "t_enter_expected",
                },
            }
            bad = {
                "event_id": "00000000-0000-0000-0000-000000000302",
                "event_type": "order_filled",
                "event_version": 1,
                "timestamp_utc": "2026-03-29T18:00:05Z",
                "ingested_at_utc": "2026-03-29T18:00:05Z",
                "source_system": "quantbridge",
                "source_component": "exec",
                "environment": "paper",
                "run_id": "run_lk",
                "session_id": "session_lk",
                "source_seq": 1,
                "trace_id": "trace_lk",
                "decision_cycle_id": dc,
                "order_ref": "ord_lk",
                "trade_id": "t_wrong",
                "symbol": "XAUUSD",
                "severity": "info",
                "payload": {
                    "order_ref": "ord_lk",
                    "fill_price": 1.0,
                    "trade_id": "t_wrong",
                    "decision_cycle_id": dc,
                },
            }
            f.write_text(json.dumps(enter) + "\n" + json.dumps(bad) + "\n", encoding="utf-8")
            report = validate_path(path)
            msgs = [i.message for i in report.issues if i.level == "error"]
            self.assertTrue(any(m.startswith("decision_cycle_trade_id_linkage_mismatch") for m in msgs))

    def test_trade_id_envelope_payload_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir)
            event_file = path / "events.jsonl"
            ev = {
                "event_id": "00000000-0000-0000-0000-000000000103",
                "event_type": "trade_executed",
                "event_version": 1,
                "timestamp_utc": "2026-03-29T18:00:00Z",
                "ingested_at_utc": "2026-03-29T18:00:01Z",
                "source_system": "quantbuild",
                "source_component": "live_runner",
                "environment": "paper",
                "run_id": "run_ep",
                "session_id": "session_ep",
                "source_seq": 1,
                "trace_id": "trace_ep",
                "trade_id": "trade_a",
                "severity": "info",
                "order_ref": "ord_ep",
                "payload": {"direction": "LONG", "trade_id": "trade_b"},
            }
            event_file.write_text(json.dumps(ev) + "\n", encoding="utf-8")
            report = validate_path(path)
            msgs = [i.message for i in report.issues if i.level == "error"]
            self.assertIn("trade_id_envelope_payload_mismatch", msgs)

    def test_market_data_stale_warning_valid_minimal_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir)
            event_file = path / "events.jsonl"
            event = {
                "event_id": "00000000-0000-0000-0000-000000000021",
                "event_type": "market_data_stale_warning",
                "event_version": 1,
                "timestamp_utc": "2026-04-14T14:58:00Z",
                "ingested_at_utc": "2026-04-14T14:58:01Z",
                "source_system": "quantbuild",
                "source_component": "live_runner",
                "environment": "live",
                "run_id": "run_stale",
                "session_id": "session_stale",
                "source_seq": 1,
                "trace_id": "trace_stale",
                "severity": "warn",
                "payload": {
                    "symbol": "XAUUSD",
                    "bar_lag_minutes": 22.5,
                    "latest_bar_ts_utc": "2026-04-14 14:30:00+00:00",
                    "session": "New York",
                    "threshold_minutes": 16.0,
                    "source_actual": "cache_fresh",
                },
            }
            event_file.write_text(json.dumps(event) + "\n", encoding="utf-8")
            report = validate_path(path)
            self.assertEqual(report.events_valid, 1)
            self.assertEqual(len([i for i in report.issues if i.level == "error"]), 0)


if __name__ == "__main__":
    unittest.main()

