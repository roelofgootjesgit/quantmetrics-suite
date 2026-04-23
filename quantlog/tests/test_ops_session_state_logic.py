"""Tests for session-state helpers (no Streamlit runtime)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
for _p in (REPO / "src", REPO / "quantlog_ops"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from utils.session_state import (  # noqa: E402
    ALL_RUNS,
    KEY_DECISION,
    KEY_EVENT_TYPE,
    KEY_PIN,
    KEY_QUICK,
    KEY_REGIME,
    KEY_RUN,
    KEY_SYMBOL,
    QUICK_ALL,
    QUICK_ENTER,
    reset_filters,
    resolve_effective_run_id,
    sanitize_run_selection,
    scope_from_run_pick,
)


class TestSessionStateLogic(unittest.TestCase):
    def test_invalid_run_fallback_to_all(self) -> None:
        state = {KEY_RUN: "missing_run"}
        sanitize_run_selection(state, ["r1", "r2"])
        self.assertEqual(state[KEY_RUN], ALL_RUNS)

    def test_invalid_pin_cleared(self) -> None:
        state = {KEY_RUN: ALL_RUNS, KEY_PIN: "ghost"}
        sanitize_run_selection(state, ["r1"])
        self.assertIsNone(state[KEY_PIN])

    def test_resolve_effective_run_id(self) -> None:
        state = {KEY_RUN: "r1"}
        rid = resolve_effective_run_id(state, ["r1", "r2"])
        self.assertEqual(rid, "r1")

    def test_scope_from_run_pick(self) -> None:
        self.assertEqual(scope_from_run_pick(ALL_RUNS), "__all__")
        self.assertEqual(scope_from_run_pick("(unknown_run)"), "__unknown__")
        self.assertEqual(scope_from_run_pick("run_a"), "run_a")

    def test_reset_filters(self) -> None:
        state = {
            KEY_QUICK: QUICK_ENTER,
            KEY_EVENT_TYPE: "foo",
            KEY_DECISION: "bar",
            KEY_SYMBOL: "X",
            KEY_REGIME: "trend",
            KEY_RUN: ALL_RUNS,
            KEY_PIN: "r_keep",
        }
        reset_filters(state, valid_ids=["r_keep", "r2"])
        self.assertEqual(state[KEY_QUICK], QUICK_ALL)
        self.assertEqual(state[KEY_EVENT_TYPE], "")
        self.assertEqual(state[KEY_RUN], "r_keep")

    def test_reset_without_valid_pin(self) -> None:
        state = {
            KEY_QUICK: QUICK_ENTER,
            KEY_EVENT_TYPE: "",
            KEY_DECISION: "",
            KEY_SYMBOL: "",
            KEY_REGIME: "",
            KEY_RUN: ALL_RUNS,
            KEY_PIN: None,
        }
        reset_filters(state, valid_ids=["r1"])
        self.assertEqual(state[KEY_RUN], ALL_RUNS)


if __name__ == "__main__":
    unittest.main()
