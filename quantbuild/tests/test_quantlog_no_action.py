"""QuantLog NO_ACTION reason mapping (live_runner contract)."""

from __future__ import annotations

import unittest

from src.quantbuild.execution.quantlog_no_action import (
    LIVE_RUNNER_NO_ACTION_INTERNAL_CODES,
    _CANONICAL_NO_ACTION,
    _INTERNAL_TO_CANONICAL,
    canonical_no_action_reason,
)


class TestQuantlogNoActionReasons(unittest.TestCase):
    def test_internal_codes_map_to_canonical(self) -> None:
        self.assertEqual(canonical_no_action_reason("news_block"), "news_filter_active")
        self.assertEqual(canonical_no_action_reason("spread_block"), "spread_too_high")
        self.assertEqual(canonical_no_action_reason("no_entry_signal"), "no_setup")
        self.assertEqual(canonical_no_action_reason("regime_block"), "regime_blocked")
        self.assertEqual(canonical_no_action_reason("outside_killzone"), "session_blocked")

    def test_already_canonical_passthrough(self) -> None:
        self.assertEqual(canonical_no_action_reason("risk_blocked"), "risk_blocked")
        self.assertEqual(canonical_no_action_reason("execution_disabled"), "execution_disabled")

    def test_unknown_defaults_to_risk_blocked(self) -> None:
        self.assertEqual(canonical_no_action_reason("totally_unknown_code"), "risk_blocked")

    def test_internal_map_targets_are_quantlog_canonical(self) -> None:
        for internal, canonical in _INTERNAL_TO_CANONICAL.items():
            self.assertIn(
                canonical,
                _CANONICAL_NO_ACTION,
                msg=f"{internal!r} -> {canonical!r} not in _CANONICAL_NO_ACTION",
            )

    def test_every_internal_code_maps_via_function(self) -> None:
        for code in LIVE_RUNNER_NO_ACTION_INTERNAL_CODES:
            out = canonical_no_action_reason(code)
            self.assertIn(out, _CANONICAL_NO_ACTION)


if __name__ == "__main__":
    unittest.main()
