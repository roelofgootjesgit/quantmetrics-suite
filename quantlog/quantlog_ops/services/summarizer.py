"""Aggregate normalized rows into KPI summaries (handbook §7.3)."""

from __future__ import annotations

from collections import Counter
from typing import Any, Iterable


def summarize(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """
    Build summary dict: totals, reasons, regimes, signal→entry proxy.

    ``rows`` must be normalized (see ``utils.parser.normalize_event``).
    """
    rows = list(rows)
    total_events = len(rows)

    signals = 0
    entries = 0
    no_action = 0
    errors = 0

    by_reason: Counter[str] = Counter()
    by_regime: Counter[str] = Counter()

    for row in rows:
        et = row.get("event_type") or ""
        sev = (row.get("_severity") or "").lower()

        if et in {"signal_evaluated", "signal_detected"}:
            signals += 1
        if et == "trade_executed":
            entries += 1
        if et == "trade_action" and (row.get("decision") or "") == "NO_ACTION":
            no_action += 1
            reason = (row.get("reason_code") or "").strip() or "unknown"
            by_reason[reason] += 1
            reg = (row.get("regime") or "").strip() or "unknown"
            by_regime[reg] += 1
        if et == "signal_filtered":
            fr = (row.get("reason_code") or "").strip() or "unknown"
            by_reason[f"filter:{fr}"] += 1

        if sev in {"error", "critical"}:
            errors += 1
        if et == "order_rejected":
            errors += 1

        if et in {"signal_evaluated", "signal_detected"}:
            reg = (row.get("regime") or "").strip()
            if reg:
                by_regime[reg] += 1

    return {
        "total_events": total_events,
        "signals": signals,
        "entries": entries,
        "no_action": no_action,
        "errors": errors,
        "by_reason": dict(by_reason.most_common()),
        "by_regime": dict(by_regime.most_common()),
    }


def dominant_reason(summary: dict[str, Any]) -> str:
    br = summary.get("by_reason") or {}
    if not br:
        return ""
    return max(br.items(), key=lambda kv: kv[1])[0]
