"""Integration: desk-grade ``signal_evaluated`` payloads pass QuantLog ``validate-events`` logic.

Requires a QuantLog checkout (sibling ``quantlog`` or ``QUANTLOG_REPO_PATH``); otherwise skips.
Does not import ``QuantLogEmitter`` (avoids optional ``filelock``); writes JSONL lines directly.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from src.quantbuild.execution.signal_evaluated_desk_grade import build_desk_grade_payload
from src.quantbuild.quantlog_repo import resolve_quantlog_repo_path


def _import_quantlog_validate_path():
    repo = resolve_quantlog_repo_path()
    if repo is None:
        return None, None
    prefix = str((repo / "src").resolve())
    if prefix not in sys.path:
        sys.path.insert(0, prefix)
    try:
        from quantlog.validate.validator import validate_path
    except ImportError:
        return None, None
    return validate_path, prefix


def _write_signal_evaluated_line(
    path: Path,
    *,
    source_seq: int,
    trace_id: str,
    decision_cycle_id: str,
    payload: dict,
    timestamp_utc: str,
    ingested_at_utc: str,
) -> None:
    event = {
        "event_id": str(uuid4()),
        "event_type": "signal_evaluated",
        "event_version": 1,
        "timestamp_utc": timestamp_utc,
        "ingested_at_utc": ingested_at_utc,
        "source_system": "quantbuild",
        "source_component": "live_runner",
        "environment": "dry_run",
        "run_id": "run_desk_grade_test",
        "session_id": "sess_desk_grade_test",
        "source_seq": source_seq,
        "trace_id": trace_id,
        "decision_cycle_id": decision_cycle_id,
        "severity": "info",
        "account_id": "acct_test",
        "strategy_id": "sqe_live_runner",
        "symbol": "XAUUSD",
        "payload": payload,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=True))
        handle.write("\n")


def _write_trade_action_terminal(
    path: Path,
    *,
    source_seq: int,
    trace_id: str,
    decision_cycle_id: str,
    timestamp_utc: str,
    ingested_at_utc: str,
    reason: str,
) -> None:
    """Terminal ``trade_action`` so QuantLog cycle validation sees a closed chain."""
    event = {
        "event_id": str(uuid4()),
        "event_type": "trade_action",
        "event_version": 1,
        "timestamp_utc": timestamp_utc,
        "ingested_at_utc": ingested_at_utc,
        "source_system": "quantbuild",
        "source_component": "live_runner",
        "environment": "dry_run",
        "run_id": "run_desk_grade_test",
        "session_id": "sess_desk_grade_test",
        "source_seq": source_seq,
        "trace_id": trace_id,
        "decision_cycle_id": decision_cycle_id,
        "severity": "info",
        "account_id": "acct_test",
        "strategy_id": "sqe_live_runner",
        "symbol": "XAUUSD",
        "payload": {"decision": "NO_ACTION", "reason": reason},
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=True))
        handle.write("\n")


class TestDeskGradeQuantlogValidation(unittest.TestCase):
    def test_signal_evaluated_desk_grade_passes_quantlog_validator(self) -> None:
        validate_path, prefix = _import_quantlog_validate_path()
        if validate_path is None:
            self.skipTest(
                "QuantLog repo or import missing — set QUANTLOG_REPO_PATH or clone "
                "quantlog beside quantbuild, and ensure quantlog dependencies are installed"
            )
        try:
            poll = datetime(2026, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
            long_ctx = {
                "structure_ok": True,
                "liquidity_pillar_ok": False,
                "trigger_ok": True,
                "combo_min_modules": 3,
                "combo_active_modules_count": 2,
                "combo_lookback_bars": 5,
                "entry_signal": False,
                "entry_path": "sweep_disp_fvg_combo",
            }
            short_ctx = {
                "structure_ok": False,
                "liquidity_pillar_ok": False,
                "trigger_ok": False,
            }
            desk = build_desk_grade_payload(
                eval_stage="no_entry_signal",
                decision_context={"long": long_ctx, "short": short_ctx},
                setup=False,
                direction="NONE",
                confidence=0.0,
                same_bar_skip_count_for_bar=0,
                previous_eval_stage_on_bar=None,
                poll_ts=poll,
                bar_ts_str="2026-06-15T12:00:00Z",
                new_bar_detected=True,
            )
            payload = {
                "signal_type": "sqe_entry",
                "signal_direction": "NONE",
                "confidence": 0.0,
                "regime": "trend",
                "session": "London",
                "setup_type": "sqe",
                "decision_cycle_id": "dc_desk_grade_1",
                "system_mode": "PRODUCTION",
                "bypassed_by_mode": [],
                **desk,
                "setup": False,
                "eval_stage": "no_entry_signal",
                "decision_context": {
                    "long": long_ctx,
                    "short": short_ctx,
                    "latest_bar_ts": "2026-06-15T12:00:00Z",
                },
            }
            ts = "2026-06-15T12:00:00Z"
            ingested = "2026-06-15T12:00:01Z"

            desk2 = build_desk_grade_payload(
                eval_stage="same_bar_already_processed",
                decision_context={
                    "latest_bar_ts": "2026-06-15T12:00:00Z",
                    "last_processed_bar_ts": "2026-06-15T12:00:00Z",
                },
                setup=False,
                direction="NONE",
                confidence=0.0,
                same_bar_skip_count_for_bar=1,
                previous_eval_stage_on_bar="no_entry_signal",
                poll_ts=poll,
                bar_ts_str="2026-06-15T12:00:00Z",
                new_bar_detected=False,
            )
            payload2 = {
                "signal_type": "sqe_entry",
                "signal_direction": "NONE",
                "confidence": 0.0,
                "regime": "trend",
                "session": "London",
                "setup_type": "sqe",
                "decision_cycle_id": "dc_desk_grade_2",
                "system_mode": "PRODUCTION",
                "bypassed_by_mode": [],
                **desk2,
                "setup": False,
                "eval_stage": "same_bar_already_processed",
                "decision_context": {
                    "latest_bar_ts": "2026-06-15T12:00:00Z",
                    "last_processed_bar_ts": "2026-06-15T12:00:00Z",
                },
            }

            with tempfile.TemporaryDirectory() as tmp_dir:
                base = Path(tmp_dir)
                jsonl = base / "2026-06-15" / "quantbuild.jsonl"
                _write_signal_evaluated_line(
                    jsonl,
                    source_seq=1,
                    trace_id="trace_desk_grade_1",
                    decision_cycle_id="dc_desk_grade_1",
                    payload=payload,
                    timestamp_utc=ts,
                    ingested_at_utc=ingested,
                )
                _write_trade_action_terminal(
                    jsonl,
                    source_seq=2,
                    trace_id="trace_desk_grade_1",
                    decision_cycle_id="dc_desk_grade_1",
                    timestamp_utc=ts,
                    ingested_at_utc=ingested,
                    reason="no_setup",
                )
                _write_signal_evaluated_line(
                    jsonl,
                    source_seq=3,
                    trace_id="trace_desk_grade_2",
                    decision_cycle_id="dc_desk_grade_2",
                    payload=payload2,
                    timestamp_utc=ts,
                    ingested_at_utc=ingested,
                )
                _write_trade_action_terminal(
                    jsonl,
                    source_seq=4,
                    trace_id="trace_desk_grade_2",
                    decision_cycle_id="dc_desk_grade_2",
                    timestamp_utc=ts,
                    ingested_at_utc=ingested,
                    reason="cooldown_active",
                )

                report = validate_path(base)
                err_msgs = [i.message for i in report.issues if i.level == "error"]
                self.assertEqual(len(err_msgs), 0, f"QuantLog validator errors: {err_msgs}")
                self.assertEqual(report.events_valid, 4)
                self.assertGreaterEqual(report.lines_scanned, 4)
        finally:
            if prefix is not None:
                try:
                    sys.path.remove(prefix)
                except ValueError:
                    pass


if __name__ == "__main__":
    unittest.main()
