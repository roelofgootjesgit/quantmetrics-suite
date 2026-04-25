from __future__ import annotations

from collections import defaultdict
from typing import Iterable

from .models import DecisionCycle

_EVENT_SLOT_MAP = {
    "signal_detected": "signal_detected",
    "signal_evaluated": "signal_evaluated",
    "risk_guard_decision": "risk_guard_decision",
    "trade_action": "trade_action",
    "order_submitted": "order_submitted",
    "order_filled": "order_filled",
    "trade_executed": "trade_executed",
    "trade_closed": "trade_closed",
    "signal_filtered": "signal_filtered",
}


def _as_float(value: object) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _event_timestamp(event: dict) -> str:
    return str(event.get("timestamp_utc") or "")


def _extract_warning(warnings: set[str], code: str) -> None:
    warnings.add(code)


def reconstruct_decision_cycles(events: list[dict]) -> list[DecisionCycle]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    fallback_index = 0
    missing_cycle_warnings = 0

    for event in events:
        cycle_id = event.get("decision_cycle_id")
        if not cycle_id:
            missing_cycle_warnings += 1
            fallback_index += 1
            cycle_id = f"missing-cycle-{fallback_index}"
        grouped[str(cycle_id)].append(event)

    cycles: list[DecisionCycle] = []
    lifecycle_warning_counts: dict[str, int] = defaultdict(int)
    if missing_cycle_warnings:
        lifecycle_warning_counts["DECISION_CYCLE_ID_MISSING"] = missing_cycle_warnings

    for cycle_id, cycle_events in grouped.items():
        ordered = sorted(cycle_events, key=_event_timestamp)
        first_event = ordered[0]
        cycle = DecisionCycle(
            decision_cycle_id=cycle_id,
            run_id=first_event.get("run_id"),
            timestamp_utc=first_event.get("timestamp_utc"),
        )

        warning_codes: set[str] = set()
        for event in ordered:
            event_type = event.get("event_type")
            slot = _EVENT_SLOT_MAP.get(str(event_type))
            if slot:
                setattr(cycle, slot, event)

            payload = event.get("payload") or {}
            cycle.symbol = cycle.symbol or payload.get("symbol")
            cycle.regime = cycle.regime or payload.get("regime")
            cycle.session = cycle.session or payload.get("session")
            cycle.direction = cycle.direction or payload.get("direction")
            cycle.guard_name = cycle.guard_name or payload.get("guard_name")
            cycle.guard_decision = cycle.guard_decision or payload.get("guard_decision") or payload.get("decision")
            cycle.action = cycle.action or payload.get("action")
            cycle.reason = cycle.reason or payload.get("reason")

            if cycle.pnl_r is None:
                cycle.pnl_r = _as_float(payload.get("pnl_r") or payload.get("payload_pnl_r"))
            if cycle.mfe_r is None:
                cycle.mfe_r = _as_float(payload.get("mfe_r") or payload.get("payload_mfe_r"))
            if cycle.mae_r is None:
                cycle.mae_r = _as_float(payload.get("mae_r") or payload.get("payload_mae_r"))

        if cycle.trade_action is None:
            _extract_warning(warning_codes, "TRADE_ACTION_MISSING")
        if cycle.risk_guard_decision is None:
            _extract_warning(warning_codes, "RISK_DECISION_MISSING")
        if cycle.trade_closed and not cycle.trade_executed:
            _extract_warning(warning_codes, "TRADE_CLOSED_WITHOUT_EXECUTION")
        if cycle.trade_executed and not cycle.risk_guard_decision:
            _extract_warning(warning_codes, "EXECUTION_WITHOUT_DECISION")

        expected_chain: Iterable[tuple[str, dict | None]] = (
            ("signal_detected", cycle.signal_detected),
            ("signal_evaluated", cycle.signal_evaluated),
            ("risk_guard_decision", cycle.risk_guard_decision),
            ("trade_action", cycle.trade_action),
        )
        missing_chain = [name for name, value in expected_chain if value is None]
        if missing_chain:
            cycle.incomplete = True
            _extract_warning(warning_codes, "CYCLE_INCOMPLETE")

        cycle.warnings = sorted(warning_codes)
        for code in cycle.warnings:
            lifecycle_warning_counts[code] += 1
        cycles.append(cycle)

    cycles.sort(key=lambda item: ((item.timestamp_utc or ""), item.decision_cycle_id))
    setattr(
        reconstruct_decision_cycles,
        "last_metadata",
        {
            "warning_counts": dict(lifecycle_warning_counts),
            "total_cycles": len(cycles),
            "incomplete_cycles": sum(1 for c in cycles if c.incomplete),
        },
    )
    return cycles

