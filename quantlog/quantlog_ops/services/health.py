"""Desk health KPI helpers (no PnL)."""

from __future__ import annotations

from typing import Any, Iterable


def count_unknown_label_events(rows: Iterable[dict[str, Any]]) -> tuple[int, int]:
    """Count rows where canonical fields were missing and mapped to ``unknown``."""
    keywords = {"symbol", "session", "regime", "event_type", "reason_code"}
    n = 0
    total = 0
    for row in rows:
        total += 1
        if any((row.get(k) or "") == "unknown" for k in keywords):
            n += 1
    return n, total


def compute_signal_ratios(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Ratios requested for desk health:

    - ``signal_evaluated -> trade_action``: trade_action count / signal_evaluated
    - ``signal_evaluated -> ENTER``: ENTER trade_action count / signal_evaluated
    """
    n_eval = 0
    n_trade_action = 0
    n_enter = 0

    for row in rows:
        et = row.get("event_type") or ""
        if et == "signal_evaluated":
            n_eval += 1
        if et == "trade_action":
            n_trade_action += 1
            if (row.get("decision") or "") == "ENTER":
                n_enter += 1

    denom = max(n_eval, 1)
    return {
        "n_signal_evaluated": n_eval,
        "n_trade_action": n_trade_action,
        "n_enter": n_enter,
        "ratio_eval_to_trade_action": n_trade_action / denom,
        "ratio_eval_to_enter": n_enter / denom,
    }
