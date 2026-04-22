"""SPRINT 1: central ``signal_evaluated`` payload builder."""
from __future__ import annotations

import pytest

from src.quantbuild.execution.signal_evaluated_payload import (
    DecisionCycleContext,
    assert_signal_evaluated_payload_complete,
    build_signal_evaluated_payload,
    merge_decision_context_blueprint,
)


def test_build_signal_evaluated_payload_required_keys() -> None:
    p = build_signal_evaluated_payload(
        decision_cycle_id="dc_test_1",
        session="London",
        regime="trend",
        signal_type="sqe_entry",
        signal_direction="LONG",
        confidence=0.75,
        system_mode="PRODUCTION",
        bypassed_by_mode=[],
        eval_stage="no_entry_signal",
        decision_context={"session": "London", "combo_active_modules_count": 2},
        desk_extra={"gate_summary": {"x": 1}},
    )
    assert_signal_evaluated_payload_complete(p)
    assert p["session"] == "London"
    assert p["setup_type"] == "sqe"
    assert p["decision_cycle_id"] == "dc_test_1"
    assert p["eval_stage"] == "no_entry_signal"
    assert p["combo_count"] == 2


def test_build_fills_session_from_decision_context() -> None:
    p = build_signal_evaluated_payload(
        decision_cycle_id="dc_x",
        session="",
        regime=None,
        signal_type="sqe_entry",
        signal_direction="NONE",
        confidence=0.0,
        system_mode="PRODUCTION",
        bypassed_by_mode=[],
        decision_context={"session": "NY", "spread_pips": 1.5},
    )
    assert_signal_evaluated_payload_complete(p)
    assert p["session"] == "NY"
    assert p["spread"] == pytest.approx(1.5)


def test_decision_cycle_context_frozen() -> None:
    ctx = DecisionCycleContext(
        decision_cycle_id="dc1", trace_id="t1", session="Asia", regime="expansion"
    )
    assert ctx.setup_type == "sqe"


def test_assert_rejects_missing_decision_cycle_id() -> None:
    p = build_signal_evaluated_payload(
        decision_cycle_id="dc_ok",
        session="London",
        regime="none",
        signal_type="sqe_entry",
        signal_direction="LONG",
        confidence=1.0,
        system_mode="PRODUCTION",
        bypassed_by_mode=[],
    )
    del p["decision_cycle_id"]
    with pytest.raises(AssertionError):
        assert_signal_evaluated_payload_complete(p)
