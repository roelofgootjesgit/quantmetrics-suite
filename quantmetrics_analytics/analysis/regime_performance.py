"""Sprint 5: regime × session breakdown (proxy until full trade PnL joins)."""

from __future__ import annotations

import pandas as pd


def format_regime_performance(df: pd.DataFrame) -> str:
    lines = ["REGIME / CONTEXT", ""]
    if df.empty:
        return "\n".join(lines) + "(no events)\n"

    ev = df[df["event_type"] == "signal_evaluated"] if "event_type" in df.columns else pd.DataFrame()
    if ev.empty:
        lines.append("  (no signal_evaluated events)")
        return "\n".join(lines) + "\n"

    if "timestamp_utc" in ev.columns:
        ev = ev.sort_values("timestamp_utc", kind="mergesort")

    if "payload_regime" in ev.columns:
        vc = ev["payload_regime"].fillna("<missing>").astype(str).value_counts()
        lines.append("  signal_evaluated by regime (volume proxy):")
        for reg, c in vc.items():
            lines.append(f"    {reg}: {c:,}")
        lines.append("")
    else:
        lines.append("  (payload_regime not present on signal_evaluated)")
        lines.append("")

    if "payload_session" in ev.columns:
        vc = ev["payload_session"].fillna("<missing>").astype(str).value_counts()
        lines.append("  signal_evaluated by session:")
        for ses, c in vc.items():
            lines.append(f"    {ses}: {c:,}")
        lines.append("")

    # Trade intent by regime via trace_id join (best-effort)
    if "trace_id" in df.columns and "payload_regime" in ev.columns:
        regimes: dict[str, str] = {}
        for _, row in ev.iterrows():
            tid = row.get("trace_id")
            reg = row.get("payload_regime")
            if tid is not None and pd.notna(tid):
                regimes[str(tid)] = str(reg) if reg is not None and pd.notna(reg) else "<missing>"

        ta = df[df["event_type"] == "trade_action"]
        ta = ta[ta["payload_decision"].astype(str).str.upper().isin(("ENTER", "REVERSE"))] if "payload_decision" in ta.columns else ta
        if not ta.empty:
            by_reg: dict[str, int] = {}
            for _, row in ta.iterrows():
                tid = row.get("trace_id")
                if tid is None or pd.isna(tid):
                    continue
                r = regimes.get(str(tid), "<unknown_trace>")
                by_reg[r] = by_reg.get(r, 0) + 1
            if by_reg:
                lines.append(
                    "  ENTER/REVERSE trade_action by regime (via trace -> last signal_evaluated):"
                )
                for reg in sorted(by_reg.keys(), key=lambda x: (-by_reg[x], x)):
                    lines.append(f"    {reg}: {by_reg[reg]:,}")
                lines.append("")

    lines.append(
        "  Expectancy per regime needs payload_pnl_r (or closed-trade events); "
        "extend schema or Sprint 4 joins when available."
    )
    return "\n".join(lines) + "\n"
