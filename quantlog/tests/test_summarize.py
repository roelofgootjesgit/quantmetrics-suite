from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from quantlog.summarize.service import summarize_path


class TestSummarize(unittest.TestCase):
    def test_no_action_reason_histogram_and_trade_decisions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir)
            f = path / "e.jsonl"
            events = [
                {
                    "event_id": "00000000-0000-0000-0000-000000000031",
                    "event_type": "trade_action",
                    "event_version": 1,
                    "timestamp_utc": "2026-03-29T18:00:00Z",
                    "ingested_at_utc": "2026-03-29T18:00:00Z",
                    "source_system": "quantbuild",
                    "source_component": "decision_engine",
                    "environment": "paper",
                    "run_id": "run_s",
                    "session_id": "session_s",
                    "source_seq": 1,
                    "trace_id": "trace_s",
                    "severity": "info",
                    "payload": {"decision": "NO_ACTION", "reason": "cooldown_active"},
                },
                {
                    "event_id": "00000000-0000-0000-0000-000000000032",
                    "event_type": "trade_action",
                    "event_version": 1,
                    "timestamp_utc": "2026-03-29T18:00:01Z",
                    "ingested_at_utc": "2026-03-29T18:00:01Z",
                    "source_system": "quantbuild",
                    "source_component": "decision_engine",
                    "environment": "paper",
                    "run_id": "run_s",
                    "session_id": "session_s",
                    "source_seq": 2,
                    "trace_id": "trace_s",
                    "severity": "info",
                    "payload": {"decision": "NO_ACTION", "reason": "cooldown_active"},
                },
                {
                    "event_id": "00000000-0000-0000-0000-000000000033",
                    "event_type": "trade_action",
                    "event_version": 1,
                    "timestamp_utc": "2026-03-29T18:00:02Z",
                    "ingested_at_utc": "2026-03-29T18:00:02Z",
                    "source_system": "quantbuild",
                    "source_component": "decision_engine",
                    "environment": "paper",
                    "run_id": "run_s",
                    "session_id": "session_s",
                    "source_seq": 3,
                    "trace_id": "trace_s",
                    "severity": "info",
                    "payload": {"decision": "ENTER", "reason": "ok"},
                },
            ]
            f.write_text("\n".join(json.dumps(e) for e in events) + "\n", encoding="utf-8")

            s = summarize_path(path)
            self.assertEqual(s.no_action_by_reason.get("cooldown_active"), 2)
            self.assertEqual(s.trade_action_by_decision.get("NO_ACTION"), 2)
            self.assertEqual(s.trade_action_by_decision.get("ENTER"), 1)
            self.assertEqual(s.trades_attempted, 1)
            self.assertEqual(s.by_severity.get("info"), 3)
            self.assertEqual(s.by_source_system.get("quantbuild"), 3)
            self.assertEqual(s.by_source_component.get("decision_engine"), 3)
            self.assertEqual(s.by_environment.get("paper"), 3)
            self.assertEqual(s.non_contract_event_types, {})
            self.assertEqual(s.count_unique_run_ids, 1)
            self.assertEqual(s.count_unique_session_ids, 1)
            self.assertEqual(s.count_unique_trace_ids, 1)

    def test_non_contract_event_types_histogram(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir)
            f = path / "e.jsonl"
            base = {
                "event_version": 1,
                "timestamp_utc": "2026-03-29T18:00:00Z",
                "ingested_at_utc": "2026-03-29T18:00:00Z",
                "source_system": "quantbuild",
                "source_component": "decision_engine",
                "environment": "paper",
                "run_id": "run_nc",
                "session_id": "session_nc",
                "trace_id": "trace_nc",
                "severity": "info",
            }
            good = {
                **base,
                "event_id": "00000000-0000-0000-0000-000000000040",
                "event_type": "trade_action",
                "source_seq": 1,
                "payload": {"decision": "NO_ACTION", "reason": "no_setup"},
            }
            bad = {
                **base,
                "event_id": "00000000-0000-0000-0000-000000000041",
                "event_type": "legacy_unknown_event_v0",
                "source_seq": 2,
                "payload": {},
            }
            f.write_text("\n".join([json.dumps(good), json.dumps(bad)]) + "\n", encoding="utf-8")
            s = summarize_path(path)
            self.assertEqual(s.non_contract_event_types.get("legacy_unknown_event_v0"), 1)
            self.assertEqual(s.by_environment.get("paper"), 2)
            self.assertEqual(s.by_source_component.get("decision_engine"), 2)
            self.assertEqual(s.count_unique_run_ids, 1)
            self.assertEqual(s.count_unique_trace_ids, 1)

    def test_count_unique_run_ids_with_two_runs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir)
            f = path / "e.jsonl"
            base = {
                "event_version": 1,
                "event_type": "trade_action",
                "timestamp_utc": "2026-03-29T18:00:00Z",
                "ingested_at_utc": "2026-03-29T18:00:00Z",
                "source_system": "quantbuild",
                "source_component": "x",
                "environment": "paper",
                "session_id": "sess_one",
                "source_seq": 1,
                "trace_id": "t1",
                "severity": "info",
                "payload": {"decision": "NO_ACTION", "reason": "no_setup"},
            }
            e1 = {**base, "event_id": "00000000-0000-0000-0000-000000000050", "run_id": "run_a"}
            e2 = {
                **base,
                "event_id": "00000000-0000-0000-0000-000000000051",
                "run_id": "run_b",
                "source_seq": 2,
                "trace_id": "t2",
            }
            f.write_text("\n".join([json.dumps(e1), json.dumps(e2)]) + "\n", encoding="utf-8")
            s = summarize_path(path)
            self.assertEqual(s.count_unique_run_ids, 2)
            self.assertEqual(s.count_unique_session_ids, 1)
            self.assertEqual(s.count_unique_trace_ids, 2)

    def test_no_action_missing_reason_bucket(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir)
            f = path / "e.jsonl"
            event = {
                "event_id": "00000000-0000-0000-0000-000000000034",
                "event_type": "trade_action",
                "event_version": 1,
                "timestamp_utc": "2026-03-29T18:00:00Z",
                "ingested_at_utc": "2026-03-29T18:00:00Z",
                "source_system": "quantbuild",
                "source_component": "decision_engine",
                "environment": "paper",
                "run_id": "run_s2",
                "session_id": "session_s2",
                "source_seq": 1,
                "trace_id": "trace_s2",
                "severity": "info",
                "payload": {"decision": "NO_ACTION"},
            }
            f.write_text(json.dumps(event) + "\n", encoding="utf-8")

            s = summarize_path(path)
            self.assertEqual(s.no_action_by_reason.get("<missing_or_empty_reason>"), 1)

    def test_risk_guard_block_by_guard_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir)
            f = path / "e.jsonl"
            event = {
                "event_id": "00000000-0000-0000-0000-000000000035",
                "event_type": "risk_guard_decision",
                "event_version": 1,
                "timestamp_utc": "2026-03-29T18:00:00Z",
                "ingested_at_utc": "2026-03-29T18:00:00Z",
                "source_system": "quantbuild",
                "source_component": "risk_engine",
                "environment": "paper",
                "run_id": "run_g",
                "session_id": "session_g",
                "source_seq": 1,
                "trace_id": "trace_g",
                "severity": "info",
                "payload": {
                    "guard_name": "spread_guard",
                    "decision": "BLOCK",
                    "reason": "wide",
                },
            }
            f.write_text(json.dumps(event) + "\n", encoding="utf-8")

            s = summarize_path(path)
            self.assertEqual(s.risk_guard_blocks_by_guard.get("spread_guard"), 1)
            self.assertEqual(s.risk_guard_by_decision.get("BLOCK"), 1)
            self.assertEqual(s.blocks_total, 1)

    def test_signal_filtered_by_reason_histogram(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir)
            f = path / "e.jsonl"
            ev = {
                "event_id": "00000000-0000-0000-0000-000000000036",
                "event_type": "signal_filtered",
                "event_version": 1,
                "timestamp_utc": "2026-03-29T18:00:00Z",
                "ingested_at_utc": "2026-03-29T18:00:00Z",
                "source_system": "quantbuild",
                "source_component": "live_runner",
                "environment": "paper",
                "run_id": "run_sf",
                "session_id": "session_sf",
                "source_seq": 1,
                "trace_id": "trace_sf",
                "severity": "info",
                "payload": {
                    "filter_reason": "regime_blocked",
                    "raw_reason": "regime_block",
                    "signal_id": "sig_x",
                },
            }
            f.write_text(json.dumps(ev) + "\n", encoding="utf-8")
            s = summarize_path(path)
            self.assertEqual(s.signal_filtered_by_reason.get("regime_blocked"), 1)
            self.assertEqual(s.non_contract_event_types, {})


if __name__ == "__main__":
    unittest.main()
