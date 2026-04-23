"""Export ``risk_guard_decision`` rows as guard_decisions grain."""

from __future__ import annotations

from typing import Any

import pandas as pd


def risk_guard_events_to_df(events: list[dict[str, Any]]) -> pd.DataFrame:
    """One row per ``risk_guard_decision`` from QuantBuild."""
    rows: list[dict[str, Any]] = []
    for ev in events:
        if ev.get("event_type") != "risk_guard_decision" or ev.get("source_system") != "quantbuild":
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
                "guard_name": pl.get("guard_name"),
                "decision": pl.get("decision"),
                "reason": pl.get("reason"),
            }
        )
    return pd.DataFrame(rows)
