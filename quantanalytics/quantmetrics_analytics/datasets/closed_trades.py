"""Export ``trade_closed`` rows as closed_trades grain."""

from __future__ import annotations

from typing import Any

import pandas as pd


def trade_closed_events_to_df(events: list[dict[str, Any]]) -> pd.DataFrame:
    """One row per ``trade_closed`` event."""
    rows: list[dict[str, Any]] = []
    for ev in events:
        if ev.get("event_type") != "trade_closed":
            continue
        pl = ev.get("payload") if isinstance(ev.get("payload"), dict) else {}
        row: dict[str, Any] = {
            "timestamp_utc": ev.get("timestamp_utc"),
            "run_id": ev.get("run_id"),
            "session_id": ev.get("session_id"),
            "trace_id": ev.get("trace_id"),
            "symbol": ev.get("symbol"),
            "trade_id": pl.get("trade_id") or ev.get("trade_id"),
            "exit_price": pl.get("exit_price"),
            "pnl_r": pl.get("pnl_r"),
            "r_multiple": pl.get("r_multiple"),
            "net_pnl": pl.get("net_pnl"),
            "entry_time_utc": pl.get("entry_time_utc"),
            "exit_time_utc": pl.get("exit_time_utc"),
            "holding_time_seconds": pl.get("holding_time_seconds"),
            "mae": pl.get("mae"),
            "mfe": pl.get("mfe"),
            "exit_reason": pl.get("exit_reason"),
            "source_system": ev.get("source_system"),
        }
        rows.append(row)
    return pd.DataFrame(rows)
