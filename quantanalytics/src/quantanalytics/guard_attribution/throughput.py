from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime
from typing import Any

from .models import DecisionCycle


def _payload(event: dict[str, Any]) -> dict[str, Any]:
    payload = event.get("payload")
    return payload if isinstance(payload, dict) else {}


def _guard_decision_from_event(event: dict[str, Any]) -> str | None:
    payload = _payload(event)
    for key in ("guard_decision", "decision"):
        value = payload.get(key)
        if value:
            return str(value).upper()
    return None


def _guard_name_from_event(event: dict[str, Any]) -> str | None:
    payload = _payload(event)
    name = payload.get("guard_name")
    return str(name) if name else None


def _regime_session_from_event(event: dict[str, Any]) -> tuple[str | None, str | None]:
    payload = _payload(event)
    regime = payload.get("regime")
    session = payload.get("session")
    return (str(regime) if regime else None, str(session) if session else None)


def _trade_action_decision(event: dict[str, Any]) -> str | None:
    payload = _payload(event)
    decision = payload.get("decision") or payload.get("action")
    return str(decision).upper() if decision else None


def _has_execution(cycle: DecisionCycle) -> bool:
    return cycle.trade_executed is not None


def _months_span_from_events(events: list[dict[str, Any]]) -> int | None:
    timestamps: list[datetime] = []
    for event in events:
        ts = event.get("timestamp_utc")
        if not ts:
            continue
        cleaned = str(ts).replace("Z", "+00:00")
        try:
            timestamps.append(datetime.fromisoformat(cleaned))
        except ValueError:
            continue
    if len(timestamps) < 2:
        return None
    timestamps.sort()
    start = timestamps[0]
    end = timestamps[-1]
    months = (end.year - start.year) * 12 + (end.month - start.month) + 1
    return max(1, months)


def analyze_throughput(events: list[dict[str, Any]], cycles: list[DecisionCycle]) -> dict[str, Any]:
    raw_signals_detected = sum(1 for e in events if str(e.get("event_type")) == "signal_detected")

    risk_events = [e for e in events if str(e.get("event_type")) == "risk_guard_decision"]
    filtered_events = [e for e in events if str(e.get("event_type")) == "signal_filtered"]
    trade_action_events = [e for e in events if str(e.get("event_type")) == "trade_action"]

    guard_decisions = Counter()
    guard_blocks = Counter()
    guard_allows = Counter()
    regime_guard_blocks: Counter[tuple[str, str]] = Counter()
    session_guard_blocks: Counter[tuple[str, str]] = Counter()
    filter_reasons = Counter()

    for event in risk_events:
        name = _guard_name_from_event(event) or "UNKNOWN_GUARD"
        decision = _guard_decision_from_event(event) or "UNKNOWN"
        guard_decisions[(name, decision)] += 1
        if decision == "BLOCK":
            guard_blocks[name] += 1
            regime, session = _regime_session_from_event(event)
            if regime:
                regime_guard_blocks[(regime, name)] += 1
            if session:
                session_guard_blocks[(session, name)] += 1
        if decision == "ALLOW":
            guard_allows[name] += 1

    for event in filtered_events:
        payload = _payload(event)
        reason = payload.get("filter_reason") or payload.get("raw_reason") or "UNKNOWN"
        filter_reasons[str(reason)] += 1

    executed_cycles = sum(1 for c in cycles if _has_execution(c))
    entered_cycles = sum(
        1
        for c in cycles
        if c.trade_action is not None and _trade_action_decision(dict(c.trade_action)) in {"ENTER", "REVERSE"}
    )

    allowed_cycles = sum(
        1
        for c in cycles
        if c.risk_guard_decision is not None and _guard_decision_from_event(dict(c.risk_guard_decision)) == "ALLOW"
    )
    blocked_cycles = sum(
        1
        for c in cycles
        if c.risk_guard_decision is not None and _guard_decision_from_event(dict(c.risk_guard_decision)) == "BLOCK"
    )

    no_action_cycles = sum(
        1
        for c in cycles
        if c.trade_action is not None and _trade_action_decision(dict(c.trade_action)) == "NO_ACTION"
    )

    # "After filters" counts only cycles that actually reached a risk decision stage.
    # Cycles without `risk_guard_decision` are treated as incomplete funnel stages
    # (they should not inflate throughput as if filters passed).
    signals_after_filters = sum(
        1
        for c in cycles
        if c.risk_guard_decision is not None
        and _guard_decision_from_event(dict(c.risk_guard_decision)) != "BLOCK"
    )

    signals_executed = executed_cycles

    filter_kill_ratio = None
    if raw_signals_detected > 0:
        filter_kill_ratio = 1.0 - (signals_after_filters / raw_signals_detected)

    execution_ratio = None
    if raw_signals_detected > 0:
        execution_ratio = signals_executed / raw_signals_detected

    months_span = _months_span_from_events(events)
    trades_per_month = (signals_executed / months_span) if months_span else None

    return {
        "raw_signals_detected": raw_signals_detected,
        "signals_after_filters": signals_after_filters,
        "signals_executed": signals_executed,
        "filter_kill_ratio": filter_kill_ratio,
        "execution_ratio": execution_ratio,
        "cycle_counts": {
            "total_cycles": len(cycles),
            "risk_allow_cycles": allowed_cycles,
            "risk_block_cycles": blocked_cycles,
            "no_action_cycles": no_action_cycles,
            "entered_cycles": entered_cycles,
            "executed_cycles": executed_cycles,
        },
        "event_counts": {
            "risk_guard_decision_events": len(risk_events),
            "signal_filtered_events": len(filtered_events),
            "trade_action_events": len(trade_action_events),
        },
        "throughput_rates": {
            "trades_per_month": trades_per_month,
            "months_span_inclusive": months_span,
        },
        "breakdowns": {
            "guard_decisions": {f"{name}:{decision}": count for (name, decision), count in guard_decisions.items()},
            "guard_blocks": dict(guard_blocks),
            "guard_allows": dict(guard_allows),
            "regime_guard_blocks": {f"{regime}:{guard}": count for (regime, guard), count in regime_guard_blocks.items()},
            "session_guard_blocks": {f"{session}:{guard}": count for (session, guard), count in session_guard_blocks.items()},
            "filter_reasons": dict(filter_reasons),
        },
    }
