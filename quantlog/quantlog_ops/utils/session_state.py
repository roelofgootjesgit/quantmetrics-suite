"""Session state helpers — testable with any MutableMapping (e.g. plain dict)."""

from __future__ import annotations

from typing import Any, MutableMapping

# Stable Streamlit / app keys (handbook §4.5)
KEY_DAY = "ops_selected_day"
KEY_RUN = "ops_selected_run_id"
KEY_EVENT_TYPE = "ops_selected_event_type"
KEY_DECISION = "ops_selected_decision"
KEY_SYMBOL = "ops_selected_symbol"
KEY_REGIME = "ops_selected_regime"
KEY_QUICK = "ops_quick_filter_mode"
KEY_PIN = "ops_pinned_run_id"

ALL_RUNS = "(all runs)"
UNKNOWN_RUN = "(unknown_run)"

QUICK_ALL = "all"
QUICK_ENTER = "enter"
QUICK_NO_ACTION = "no_action"
QUICK_ERRORS = "errors"
QUICK_UNKNOWN = "unknown"


def ensure_session_defaults(state: MutableMapping[str, Any]) -> None:
    """Initialize missing keys without wiping user choices."""
    state.setdefault(KEY_QUICK, QUICK_ALL)
    state.setdefault(KEY_EVENT_TYPE, "")
    state.setdefault(KEY_DECISION, "")
    state.setdefault(KEY_SYMBOL, "")
    state.setdefault(KEY_REGIME, "")
    state.setdefault(KEY_RUN, ALL_RUNS)
    state.setdefault(KEY_PIN, None)


def get_selected_day(state: MutableMapping[str, Any]) -> str | None:
    v = state.get(KEY_DAY)
    return str(v) if v is not None else None


def set_selected_day(state: MutableMapping[str, Any], day: str | None) -> None:
    state[KEY_DAY] = day


def get_selected_run_id(state: MutableMapping[str, Any]) -> str:
    v = state.get(KEY_RUN)
    return str(v) if v else ALL_RUNS


def set_selected_run_id(state: MutableMapping[str, Any], run_id: str) -> None:
    state[KEY_RUN] = run_id


def get_quick_filter_mode(state: MutableMapping[str, Any]) -> str:
    v = state.get(KEY_QUICK, QUICK_ALL)
    return str(v) if v else QUICK_ALL


def set_quick_filter_mode(state: MutableMapping[str, Any], mode: str) -> None:
    state[KEY_QUICK] = mode


def get_pinned_run_id(state: MutableMapping[str, Any]) -> str | None:
    p = state.get(KEY_PIN)
    if p is None or p == "":
        return None
    return str(p)


def set_pinned_run_id(state: MutableMapping[str, Any], run_id: str | None) -> None:
    state[KEY_PIN] = run_id


def valid_run_ids_for_day(idx: dict[str, Any]) -> list[str]:
    return [r["run_id"] for r in idx.get("runs", [])]


def sanitize_run_selection(
    state: MutableMapping[str, Any],
    valid_ids: list[str],
) -> str:
    """If current selection not in valid_ids, reset to ALL_RUNS and clear invalid pin."""
    sel = get_selected_run_id(state)
    valid = set(valid_ids)
    if sel != ALL_RUNS and sel not in valid:
        set_selected_run_id(state, ALL_RUNS)
        sel = ALL_RUNS
    pin = get_pinned_run_id(state)
    if pin is not None and pin not in valid:
        set_pinned_run_id(state, None)
    return get_selected_run_id(state)


def apply_pin_as_default_selection(
    state: MutableMapping[str, Any],
    valid_ids: list[str],
) -> None:
    """If nothing concrete selected, adopt pinned run when valid."""
    sel = get_selected_run_id(state)
    valid = set(valid_ids)
    pin = get_pinned_run_id(state)
    if sel == ALL_RUNS and pin is not None and pin in valid:
        set_selected_run_id(state, pin)


def resolve_effective_run_id(
    state: MutableMapping[str, Any],
    valid_ids: list[str],
) -> str:
    """Return UI run id after sanitization (ALL_RUNS or concrete run key)."""
    sanitize_run_selection(state, valid_ids)
    return get_selected_run_id(state)


def scope_from_run_pick(run_pick: str) -> str:
    """Map sidebar value to ``cached_load_bounded`` scope token."""
    if run_pick == ALL_RUNS:
        return "__all__"
    if run_pick == UNKNOWN_RUN:
        return "__unknown__"
    return run_pick


def reset_filters(
    state: MutableMapping[str, Any],
    *,
    valid_ids: list[str],
) -> None:
    """Reset quick + detail filters; run → pinned if valid else ALL_RUNS."""
    set_quick_filter_mode(state, QUICK_ALL)
    state[KEY_EVENT_TYPE] = ""
    state[KEY_DECISION] = ""
    state[KEY_SYMBOL] = ""
    state[KEY_REGIME] = ""
    pin = get_pinned_run_id(state)
    if pin is not None and pin in set(valid_ids):
        set_selected_run_id(state, pin)
    else:
        set_selected_run_id(state, ALL_RUNS)


def format_copy_block(
    *,
    day: str,
    events_root: str,
    effective_run: str,
    pinned: str | None,
    quick_mode: str,
    rows_loaded: int,
    table_cap: int,
    health_cap: int,
    explainer_cap: int,
) -> str:
    lines = [
        f"Day: {day}",
        f"Run (effective): {effective_run}",
        f"Pinned: {pinned or '—'}",
        f"Quick filter: {quick_mode}",
        f"Rows loaded (table slice): {rows_loaded}",
        f"Table cap: {table_cap}",
        f"Health cap: {health_cap}",
        f"Explainer cap: {explainer_cap}",
        f"Events root: {events_root}",
    ]
    return "\n".join(lines)
