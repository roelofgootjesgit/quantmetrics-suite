"""Sprint 1: event inventory (totals + event_type distribution)."""

from __future__ import annotations

import pandas as pd


def format_event_summary(df: pd.DataFrame) -> str:
    if df.empty:
        return "Total events: 0\n(no rows after load/parse)\n"
    n = len(df)
    if "event_type" not in df.columns:
        return f"Total events: {n}\n(missing event_type column - check JSONL schema)\n"
    counts = df["event_type"].value_counts()
    lines = [f"Total events: {n:,}", "", "Event types:"]
    for et, c in counts.items():
        lines.append(f"  - {et}: {c:,}")
    extra = _format_setup_funnel_addon(df) + _format_hyp002_funnel_addon(df)
    return "\n".join(lines) + extra


def _format_hyp002_funnel_addon(df: pd.DataFrame) -> str:
    """HYP-002 event funnel when sweep_detected / sweep_classified rows exist."""
    if df.empty or "event_type" not in df.columns:
        return ""
    if not (df["event_type"] == "sweep_detected").any():
        return ""
    out = ["", "HYP-002 funnel (QuantBuild ny_sweep_failure_reclaim):"]
    for et in (
        "setup_candidate",
        "sweep_detected",
        "sweep_classified",
        "reclaim_entry_signal",
        "trade_executed",
    ):
        out.append(f"  {et}: {int((df['event_type'] == et).sum()):,}")
    sc = df[df["event_type"] == "sweep_classified"]
    if not sc.empty and "payload_result" in sc.columns:
        for res, cnt in sc["payload_result"].value_counts().sort_index().items():
            out.append(f"  sweep_classified[{res}]: {int(cnt):,}")
    return "\n".join(out) + "\n"


def _format_setup_funnel_addon(df: pd.DataFrame) -> str:
    """Counts setup_candidate + setup_rejected reasons when present (NY sweep funnel)."""
    if df.empty or "event_type" not in df.columns:
        return "\n"
    cand_n = int((df["event_type"] == "setup_candidate").sum())
    rej = df[df["event_type"] == "setup_rejected"]
    if cand_n == 0 and rej.empty:
        return "\n"
    out = ["", "Setup funnel (QuantBuild ny_sweep_reversion):"]
    out.append(f"  setup_candidate: {cand_n:,}")
    if not rej.empty and "payload_reason" in rej.columns:
        for reason, cnt in rej["payload_reason"].value_counts().sort_index().items():
            out.append(f"  setup_rejected[{reason}]: {int(cnt):,}")
    elif not rej.empty:
        out.append(f"  setup_rejected (total): {len(rej):,} (no payload_reason column)")
    return "\n".join(out) + "\n"
