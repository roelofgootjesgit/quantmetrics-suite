from __future__ import annotations

import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


@pytest.fixture
def sample_cycle_events() -> list[dict]:
    return [
        {
            "event_type": "signal_detected",
            "timestamp_utc": "2026-04-25T04:21:36Z",
            "run_id": "qb_run_20260425T042136Z_dbd1b0cc",
            "decision_cycle_id": "dc-1",
            "payload": {"symbol": "ES", "regime": "TREND", "session": "EU"},
        },
        {
            "event_type": "signal_evaluated",
            "timestamp_utc": "2026-04-25T04:21:37Z",
            "run_id": "qb_run_20260425T042136Z_dbd1b0cc",
            "decision_cycle_id": "dc-1",
            "payload": {"direction": "LONG"},
        },
        {
            "event_type": "risk_guard_decision",
            "timestamp_utc": "2026-04-25T04:21:38Z",
            "run_id": "qb_run_20260425T042136Z_dbd1b0cc",
            "decision_cycle_id": "dc-1",
            "payload": {"guard_name": "spread_guard", "guard_decision": "ALLOW"},
        },
        {
            "event_type": "trade_action",
            "timestamp_utc": "2026-04-25T04:21:39Z",
            "run_id": "qb_run_20260425T042136Z_dbd1b0cc",
            "decision_cycle_id": "dc-1",
            "payload": {"action": "ENTER"},
        },
        {
            "event_type": "trade_executed",
            "timestamp_utc": "2026-04-25T04:21:40Z",
            "run_id": "qb_run_20260425T042136Z_dbd1b0cc",
            "decision_cycle_id": "dc-1",
            "payload": {},
        },
        {
            "event_type": "trade_closed",
            "timestamp_utc": "2026-04-25T04:21:50Z",
            "run_id": "qb_run_20260425T042136Z_dbd1b0cc",
            "decision_cycle_id": "dc-1",
            "payload": {"pnl_r": 1.2, "mfe_r": 1.5, "mae_r": 0.2},
        },
    ]

