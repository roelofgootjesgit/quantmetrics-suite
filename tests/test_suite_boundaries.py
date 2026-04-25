from __future__ import annotations

from pathlib import Path

from src.quantbuild.execution.signal_evaluated_payload import (
    assert_signal_evaluated_payload_complete,
    build_signal_evaluated_payload,
)
from quantmetrics_os.scripts.data_lifecycle import _scan_runs


def test_quantbuild_can_build_decision_payload() -> None:
    payload = build_signal_evaluated_payload(
        decision_cycle_id="dc_demo_test",
        session="London",
        regime="trend",
        signal_type="sqe_entry",
        signal_direction="LONG",
        confidence=0.73,
        system_mode="PRODUCTION",
        bypassed_by_mode=[],
        eval_stage="all_checks_passed",
    )
    assert_signal_evaluated_payload_complete(payload)
    assert payload["decision_cycle_id"] == "dc_demo_test"


def test_quantmetrics_os_finds_run_artifacts() -> None:
    root = Path(__file__).resolve().parents[1]
    qmos_root = root / "quantmetrics_os"
    rows = _scan_runs(runs_root=qmos_root / "runs", qmos_root=qmos_root)
    assert rows, "Expected at least one run artifact folder under quantmetrics_os/runs"
