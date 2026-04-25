from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class DecisionCycle:
    decision_cycle_id: str
    run_id: str | None
    timestamp_utc: str | None

    signal_detected: dict | None = None
    signal_evaluated: dict | None = None
    risk_guard_decision: dict | None = None
    trade_action: dict | None = None
    order_submitted: dict | None = None
    order_filled: dict | None = None
    trade_executed: dict | None = None
    trade_closed: dict | None = None
    signal_filtered: dict | None = None

    symbol: str | None = None
    regime: str | None = None
    session: str | None = None
    direction: str | None = None

    guard_name: str | None = None
    guard_decision: str | None = None
    action: str | None = None
    reason: str | None = None

    pnl_r: float | None = None
    mfe_r: float | None = None
    mae_r: float | None = None

    warnings: list[str] = field(default_factory=list)
    incomplete: bool = False

