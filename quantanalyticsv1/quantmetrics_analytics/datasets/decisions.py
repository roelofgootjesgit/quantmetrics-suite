"""Export ``trade_action`` rows as a decisions grain (one row per terminal decision)."""

from __future__ import annotations

from typing import Any

import pandas as pd


def trade_actions_to_decisions_df(events: list[dict[str, Any]]) -> pd.DataFrame:
    """QuantBuild ``trade_action`` only; envelope correlation fields + payload decision/reason/trade_id."""
    rows: list[dict[str, Any]] = []
    for ev in events:
        if ev.get("event_type") != "trade_action" or ev.get("source_system") != "quantbuild":
            continue
        pl = ev.get("payload") if isinstance(ev.get("payload"), dict) else {}
        rows.append(
            {
                "timestamp_utc": ev.get("timestamp_utc"),
                "run_id": ev.get("run_id"),
                "session_id": ev.get("session_id"),
                "trace_id": ev.get("trace_id"),
                "decision_cycle_id": ev.get("decision_cycle_id"),
                "symbol": ev.get("symbol"),
                "decision": pl.get("decision"),
                "reason": pl.get("reason"),
                "trade_id": pl.get("trade_id"),
            }
        )
    return pd.DataFrame(rows)
