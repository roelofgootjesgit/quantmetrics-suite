"""Sprint 4: trade / execution performance when numeric fields exist."""

from __future__ import annotations

import pandas as pd


def format_performance_summary(df: pd.DataFrame) -> str:
    lines = ["PERFORMANCE", ""]
    if df.empty:
        return "\n".join(lines) + "(no events)\n"

    ta = df[df["event_type"] == "trade_action"] if "event_type" in df.columns else pd.DataFrame()
    fills = df[df["event_type"] == "order_filled"] if "event_type" in df.columns else pd.DataFrame()

    lines.append(f"  trade_action events: {len(ta):,}")
    lines.append(f"  order_filled events: {len(fills):,}")

    numeric_candidates = ("payload_pnl_r", "payload_pnl", "payload_r_multiple", "payload_mae_r", "payload_mfe_r")
    present = [c for c in numeric_candidates if c in df.columns]
    if not present:
        lines.append("")
        lines.append(
            "  (No standard PnL / R columns in this dataset yet - "
            "extend logging or add joins for MAE/MFE/expectancy.)"
        )
        return "\n".join(lines) + "\n"

    lines.append("")
    lines.append("  Numeric payload columns present: " + ", ".join(present))
    for col in present:
        series = pd.to_numeric(df[col], errors="coerce").dropna()
        if series.empty:
            continue
        lines.append(f"  {col}: n={len(series)} mean={series.mean():.4f} median={series.median():.4f}")
    return "\n".join(lines) + "\n"
