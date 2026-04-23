"""Unit tests for QuantLog desk-grade signal_evaluated payload helpers."""

from __future__ import annotations

import unittest
from datetime import datetime, timezone

from src.quantbuild.execution.signal_evaluated_desk_grade import build_desk_grade_payload


class TestDeskGrade(unittest.TestCase):
    def test_same_bar_guard_summary(self) -> None:
        poll = datetime(2026, 4, 17, 14, 31, 25, tzinfo=timezone.utc)
        out = build_desk_grade_payload(
            eval_stage="same_bar_already_processed",
            decision_context={"latest_bar_ts": "2026-04-17T14:30:00Z"},
            setup=False,
            direction="NONE",
            confidence=0.0,
            same_bar_skip_count_for_bar=2,
            previous_eval_stage_on_bar="no_entry_signal",
            poll_ts=poll,
            bar_ts_str="2026-04-17T14:30:00Z",
            new_bar_detected=False,
        )
        self.assertFalse(out["new_bar_detected"])
        self.assertEqual(out["same_bar_guard_reason"], "last_processed_bar_ts_matches_latest_bar_ts")
        self.assertEqual(out["blocked_by_primary_gate"], "same_bar_guard")
        self.assertEqual(out["gate_summary"]["same_bar_guard"], "fail")

    def test_no_entry_merged_pillars(self) -> None:
        poll = datetime(2026, 4, 17, 15, 0, 0, tzinfo=timezone.utc)
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
        out = build_desk_grade_payload(
            eval_stage="no_entry_signal",
            decision_context={"long": long_ctx, "short": short_ctx},
            setup=False,
            direction="NONE",
            confidence=0.0,
            same_bar_skip_count_for_bar=0,
            previous_eval_stage_on_bar=None,
            poll_ts=poll,
            bar_ts_str="2026-04-17T15:00:00Z",
            new_bar_detected=True,
        )
        self.assertEqual(out["blocked_by_primary_gate"], "liquidity_gate")
        self.assertAlmostEqual(out["near_entry_score"], 2 / 3.0, places=4)
        self.assertIn("threshold_snapshot", out)


if __name__ == "__main__":
    unittest.main()
