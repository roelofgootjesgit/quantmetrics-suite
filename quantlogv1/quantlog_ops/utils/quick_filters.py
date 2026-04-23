"""Central quick-filter predicates (Sprint B) — single source of truth."""

from __future__ import annotations

from typing import Any, Literal

from utils.session_state import (
    QUICK_ALL,
    QUICK_ENTER,
    QUICK_ERRORS,
    QUICK_NO_ACTION,
    QUICK_UNKNOWN,
)

QuickMode = Literal["all", "enter", "no_action", "errors", "unknown"]

ERROR_EVENT_TYPES = frozenset(
    {
        "order_rejected",
        "failsafe_pause",
        "audit_gap_detected",
    }
)

UNKNOWN_FIELDS = frozenset(
    {"event_type", "symbol", "session", "regime", "decision", "reason_code"}
)


def is_enter_row(row: dict[str, Any]) -> bool:
    """ENTER decision or executed fill rows."""
    et = row.get("event_type") or ""
    if et == "trade_executed":
        return True
    if et == "trade_action" and (row.get("decision") or "") == "ENTER":
        return True
    return False


def is_no_action_row(row: dict[str, Any]) -> bool:
    return (row.get("event_type") or "") == "trade_action" and (
        row.get("decision") or ""
    ) == "NO_ACTION"


def is_error_row(row: dict[str, Any]) -> bool:
    """Severity, fatal-ish event types, or explicit ERROR decision."""
    sev = str(row.get("_severity") or "").lower()
    if sev in {"error", "critical"}:
        return True
    et = str(row.get("event_type") or "")
    if et == "error" or et.lower() == "error":
        return True
    if et in ERROR_EVENT_TYPES:
        return True
    if (row.get("decision") or "").upper() == "ERROR":
        return True
    return False


def is_unknown_row(row: dict[str, Any]) -> bool:
    for k in UNKNOWN_FIELDS:
        if (row.get(k) or "") == "unknown":
            return True
    return False


def apply_quick_filter(
    rows: list[dict[str, Any]],
    mode: str,
) -> list[dict[str, Any]]:
    """Filter normalized rows by quick mode."""
    m = (mode or QUICK_ALL).lower()
    if m == QUICK_ALL:
        return list(rows)
    if m == QUICK_ENTER:
        return [r for r in rows if is_enter_row(r)]
    if m == QUICK_NO_ACTION:
        return [r for r in rows if is_no_action_row(r)]
    if m == QUICK_ERRORS:
        return [r for r in rows if is_error_row(r)]
    if m == QUICK_UNKNOWN:
        return [r for r in rows if is_unknown_row(r)]
    return list(rows)


def quick_mode_label(mode: str) -> str:
    labels = {
        QUICK_ALL: "All",
        QUICK_ENTER: "ENTER only",
        QUICK_NO_ACTION: "NO_ACTION only",
        QUICK_ERRORS: "Errors only",
        QUICK_UNKNOWN: "Unknown only",
    }
    return labels.get(mode.lower(), mode)
