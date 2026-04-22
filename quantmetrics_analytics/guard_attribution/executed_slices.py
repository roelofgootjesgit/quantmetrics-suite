"""Build executed trade rows with signal context for slice statistics."""

from __future__ import annotations

from typing import Any

import pandas as pd

from quantmetrics_analytics.guard_attribution.block_extractor import _decision_cycle_id
from quantmetrics_analytics.guard_attribution.normalize import norm_key


def trade_closed_rows(events: list[dict[str, Any]]) -> pd.DataFrame:
    """Closed trades including ``decision_cycle_id`` from envelope or payload."""
    rows: list[dict[str, Any]] = []
    for ev in events:
        if ev.get("event_type") != "trade_closed":
            continue
        pl = ev.get("payload") if isinstance(ev.get("payload"), dict) else {}
        dcid = _decision_cycle_id(ev)
        if not dcid:
            dcid = str(pl.get("decision_cycle_id") or "").strip()
        pnl = pl.get("pnl_r")
        try:
            pnl_r = float(pnl) if pnl is not None else float("nan")
        except (TypeError, ValueError):
            pnl_r = float("nan")
        rows.append(
            {
                "timestamp_utc": ev.get("timestamp_utc"),
                "run_id": ev.get("run_id"),
                "trade_id": pl.get("trade_id"),
                "decision_cycle_id": dcid,
                "symbol": ev.get("symbol"),
                "session": norm_key(pl.get("session")),
                "regime": norm_key(pl.get("regime")),
                "signal_direction": norm_key(pl.get("direction")),
                "pnl_r": pnl_r,
                "source_system": ev.get("source_system"),
            }
        )
    return pd.DataFrame(rows)


def enrich_closed_with_signals(closed: pd.DataFrame, sig_idx: pd.DataFrame) -> pd.DataFrame:
    """Attach ``setup_type`` / ``signal_type`` from ``signal_evaluated`` when DCID matches."""
    if closed.empty:
        return closed
    if sig_idx.empty:
        out = closed.copy()
        out["setup_type"] = "unknown"
        out["signal_type"] = "unknown"
        return out
    m = closed.merge(
        sig_idx[["decision_cycle_id", "setup_type", "signal_type"]],
        on="decision_cycle_id",
        how="left",
    )
    m["setup_type"] = m["setup_type"].fillna("unknown").astype(str).map(norm_key)
    m["signal_type"] = m["signal_type"].fillna("unknown").astype(str).map(norm_key)
    return m
