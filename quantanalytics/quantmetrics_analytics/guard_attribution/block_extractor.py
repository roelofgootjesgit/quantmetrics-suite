"""Guard Block Extractor — risk_guard_decision rows joined with signal_evaluated context."""

from __future__ import annotations

from typing import Any

import pandas as pd

from quantmetrics_analytics.guard_attribution.normalize import norm_key


def _decision_cycle_id(ev: dict[str, Any]) -> str:
    pl = ev.get("payload") if isinstance(ev.get("payload"), dict) else {}
    for k in ("decision_cycle_id",):
        v = ev.get(k) or pl.get(k)
        if v is not None and str(v).strip():
            return str(v).strip()
    return ""


def signal_evaluated_index(events: list[dict[str, Any]]) -> pd.DataFrame:
    """Latest ``signal_evaluated`` per ``decision_cycle_id`` (QuantBuild source)."""
    rows: list[dict[str, Any]] = []
    for ev in events:
        if ev.get("event_type") != "signal_evaluated" or ev.get("source_system") != "quantbuild":
            continue
        pl = ev.get("payload") if isinstance(ev.get("payload"), dict) else {}
        dcid = _decision_cycle_id(ev)
        if not dcid:
            continue
        rows.append(
            {
                "decision_cycle_id": dcid,
                "timestamp_utc": ev.get("timestamp_utc"),
                "symbol": ev.get("symbol"),
                "session": norm_key(pl.get("session")),
                "regime": norm_key(pl.get("regime")),
                "setup_type": norm_key(pl.get("setup_type")),
                "signal_type": norm_key(pl.get("signal_type")),
                "signal_direction": norm_key(pl.get("signal_direction")),
                "confidence": pl.get("confidence"),
            }
        )
    if not rows:
        return pd.DataFrame(
            columns=[
                "decision_cycle_id",
                "timestamp_utc",
                "symbol",
                "session",
                "regime",
                "setup_type",
                "signal_type",
                "signal_direction",
                "confidence",
            ]
        )
    df = pd.DataFrame(rows)
    df = df.sort_values("timestamp_utc", na_position="last")
    return df.groupby("decision_cycle_id", as_index=False).last()


def extract_guard_blocks(events: list[dict[str, Any]], *, block_decisions: frozenset[str] | None = None) -> pd.DataFrame:
    """One row per blocking ``risk_guard_decision`` (default: ``BLOCK`` only)."""
    bd = block_decisions or frozenset({"BLOCK"})
    rows: list[dict[str, Any]] = []
    for ev in events:
        if ev.get("event_type") != "risk_guard_decision" or ev.get("source_system") != "quantbuild":
            continue
        pl = ev.get("payload") if isinstance(ev.get("payload"), dict) else {}
        decision = str(pl.get("decision") or "").strip().upper()
        if decision not in bd:
            continue
        dcid = _decision_cycle_id(ev)
        rows.append(
            {
                "timestamp_utc": ev.get("timestamp_utc"),
                "run_id": ev.get("run_id"),
                "session_id": ev.get("session_id"),
                "trace_id": ev.get("trace_id"),
                "decision_cycle_id": dcid,
                "symbol": ev.get("symbol"),
                "guard_name": pl.get("guard_name"),
                "guard_decision": decision,
                "reason": pl.get("reason"),
            }
        )
    return pd.DataFrame(rows)


def join_blocks_with_signal_context(blocks: pd.DataFrame, sig_idx: pd.DataFrame) -> pd.DataFrame:
    """Left-join blocks to signal context on ``decision_cycle_id``."""
    if blocks.empty:
        return blocks
    if sig_idx.empty:
        out = blocks.copy()
        for c in ("session", "regime", "setup_type", "signal_type", "signal_direction", "confidence"):
            out[c] = None
        return out
    merged = blocks.merge(
        sig_idx[
            [
                "decision_cycle_id",
                "session",
                "regime",
                "setup_type",
                "signal_type",
                "signal_direction",
                "confidence",
            ]
        ],
        on="decision_cycle_id",
        how="left",
    )
    for col in ("session", "regime", "setup_type", "signal_type", "signal_direction"):
        if col in merged.columns:
            merged[col] = merged[col].fillna("unknown").astype(str).map(norm_key)
    return merged
