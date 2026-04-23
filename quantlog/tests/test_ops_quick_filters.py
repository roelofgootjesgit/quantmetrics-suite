"""Tests for central quick-filter predicates (Sprint B)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
for _p in (REPO / "src", REPO / "quantlog_ops"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from utils.parser import normalize_event  # noqa: E402
from utils.quick_filters import (  # noqa: E402
    apply_quick_filter,
    is_enter_row,
    is_error_row,
    is_no_action_row,
    is_unknown_row,
)
from utils.session_state import QUICK_ENTER, QUICK_ERRORS, QUICK_NO_ACTION, QUICK_UNKNOWN


class TestQuickFilters(unittest.TestCase):
    def test_enter_only_rows(self) -> None:
        rows = [
            normalize_event(
                {
                    "timestamp_utc": "2026-04-19T08:00:00Z",
                    "run_id": "r",
                    "event_type": "trade_action",
                    "source_system": "quantbuild",
                    "severity": "info",
                    "payload": {"decision": "ENTER", "reason": "ok"},
                }
            ),
            normalize_event(
                {
                    "timestamp_utc": "2026-04-19T08:01:00Z",
                    "run_id": "r",
                    "event_type": "trade_action",
                    "source_system": "quantbuild",
                    "severity": "info",
                    "payload": {"decision": "NO_ACTION", "reason": "cooldown_active"},
                }
            ),
        ]
        self.assertTrue(is_enter_row(rows[0]))
        out = apply_quick_filter(rows, QUICK_ENTER)
        self.assertEqual(len(out), 1)

    def test_no_action_only(self) -> None:
        rows = [
            normalize_event(
                {
                    "timestamp_utc": "2026-04-19T08:00:00Z",
                    "run_id": "r",
                    "event_type": "trade_action",
                    "payload": {"decision": "NO_ACTION", "reason": "no_setup"},
                }
            ),
            normalize_event(
                {
                    "timestamp_utc": "2026-04-19T08:01:00Z",
                    "run_id": "r",
                    "event_type": "trade_action",
                    "payload": {"decision": "ENTER", "reason": "ok"},
                }
            ),
        ]
        self.assertTrue(is_no_action_row(rows[0]))
        out = apply_quick_filter(rows, QUICK_NO_ACTION)
        self.assertEqual(len(out), 1)

    def test_errors_only(self) -> None:
        rows = [
            normalize_event(
                {
                    "timestamp_utc": "2026-04-19T08:00:00Z",
                    "run_id": "r",
                    "event_type": "signal_evaluated",
                    "severity": "info",
                    "payload": {},
                }
            ),
            normalize_event(
                {
                    "timestamp_utc": "2026-04-19T08:01:00Z",
                    "run_id": "r",
                    "event_type": "order_rejected",
                    "severity": "warn",
                    "payload": {"order_ref": "x"},
                }
            ),
            normalize_event(
                {
                    "timestamp_utc": "2026-04-19T08:02:00Z",
                    "run_id": "r",
                    "event_type": "trade_action",
                    "severity": "error",
                    "source_system": "quantbuild",
                    "payload": {"decision": "NO_ACTION", "reason": "x"},
                }
            ),
        ]
        self.assertTrue(is_error_row(rows[1]))
        self.assertTrue(is_error_row(rows[2]))
        out = apply_quick_filter(rows, QUICK_ERRORS)
        self.assertEqual(len(out), 2)

    def test_unknown_only(self) -> None:
        rows = [
            normalize_event(
                {
                    "timestamp_utc": "2026-04-19T08:00:00Z",
                    "run_id": "r",
                    "event_type": "trade_action",
                    "source_system": "quantbuild",
                    "symbol": "XAUUSD",
                    "payload": {
                        "decision": "ENTER",
                        "reason": "ok",
                        "session": "London",
                        "regime": "trend",
                    },
                }
            ),
            normalize_event(
                {
                    "timestamp_utc": "2026-04-19T08:01:00Z",
                    "run_id": "",
                    "event_type": "unknown",
                    "payload": {},
                }
            ),
        ]
        self.assertFalse(is_unknown_row(rows[0]))
        self.assertTrue(is_unknown_row(rows[1]))
        out = apply_quick_filter(rows, QUICK_UNKNOWN)
        self.assertEqual(len(out), 1)


if __name__ == "__main__":
    unittest.main()
