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
    return "\n".join(lines) + "\n"
