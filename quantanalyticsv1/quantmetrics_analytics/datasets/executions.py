"""Export execution lifecycle rows (order submit + fill + trade_executed) as executions grain."""

from __future__ import annotations

from typing import Any

import pandas as pd

_EXECUTION_TYPES = frozenset({"order_submitted", "order_filled", "trade_executed"})


def execution_events_to_df(events: list[dict[str, Any]]) -> pd.DataFrame:
    """One row per execution-related event (typically QuantBridge source_system)."""
    rows: list[dict[str, Any]] = []
    for ev in events:
        et = ev.get("event_type")
        if et not in _EXECUTION_TYPES:
            continue
        pl = ev.get("payload") if isinstance(ev.get("payload"), dict) else {}
        row: dict[str, Any] = {
            "timestamp_utc": ev.get("timestamp_utc"),
            "event_type": et,
            "source_system": ev.get("source_system"),
            "run_id": ev.get("run_id"),
            "session_id": ev.get("session_id"),
            "trace_id": ev.get("trace_id"),
            "symbol": ev.get("symbol"),
            "account_id": ev.get("account_id") or pl.get("account_id"),
            "strategy_id": ev.get("strategy_id") or pl.get("strategy_id"),
            "trade_id": ev.get("trade_id") or pl.get("trade_id"),
            "order_ref": ev.get("order_ref") or pl.get("order_ref"),
            "decision_cycle_id": ev.get("decision_cycle_id") or pl.get("decision_cycle_id"),
        }
        # Fill-specific numeric fields when present on payload
        for k in (
            "requested_price",
            "fill_price",
            "slippage",
            "fill_latency_ms",
            "spread_at_fill",
            "volume",
            "side",
            "direction",
        ):
            if k in pl:
                row[k] = pl[k]
        rows.append(row)
    return pd.DataFrame(rows)
