"""Sprint 2: NO_ACTION reason breakdown (QuantLog trade_action)."""

from __future__ import annotations

import pandas as pd


def _col(df: pd.DataFrame, name: str) -> pd.Series | None:
    return df[name] if name in df.columns else None


def no_action_distribution_dict(df: pd.DataFrame) -> dict[str, dict[str, float | int]]:
    """Structured NO_ACTION counts and percentages (keys = reason strings)."""
    et = _col(df, "event_type")
    if df.empty or et is None:
        return {}
    trade = df[et == "trade_action"]
    if trade.empty:
        return {}
    dec = _col(trade, "payload_decision")
    if dec is None:
        return {}
    dec_u = dec.astype(str).str.strip().str.upper()
    no_action = trade[dec_u == "NO_ACTION"]
    if no_action.empty:
        return {}
    reason = _col(no_action, "payload_reason")
    if reason is None:
        return {}
    n = int(len(no_action))
    counts = reason.fillna("<missing>").astype(str).str.strip()
    counts = counts.replace("", "<empty>")
    vc = counts.value_counts()
    out: dict[str, dict[str, float | int]] = {}
    for r, c in vc.items():
        pct = 100.0 * float(c) / float(n) if n else 0.0
        out[str(r)] = {"count": int(c), "pct_of_no_action": round(pct, 2)}
    return out


def format_no_trade_analysis(df: pd.DataFrame) -> str:
    if df.empty:
        return "NO TRADE ANALYSIS\n(no events)\n"
    et = _col(df, "event_type")
    if et is None:
        return "NO TRADE ANALYSIS\n(missing event_type)\n"
    trade = df[et == "trade_action"]
    if trade.empty:
        return "NO TRADE ANALYSIS\n(no trade_action events)\n"
    dec = _col(trade, "payload_decision")
    if dec is None:
        return "NO TRADE ANALYSIS\n(trade_action without payload_decision)\n"
    dec_u = dec.astype(str).str.strip().str.upper()
    no_action = trade[dec_u == "NO_ACTION"]
    if no_action.empty:
        return "NO TRADE ANALYSIS\n(no trade_action with decision=NO_ACTION)\n"
    reason = _col(no_action, "payload_reason")
    if reason is None:
        return "NO TRADE ANALYSIS\n(NO_ACTION rows without payload_reason)\n"
    n = int(len(no_action))
    counts = reason.fillna("<missing>").astype(str).str.strip()
    counts = counts.replace("", "<empty>")
    vc = counts.value_counts()
    lines = ["NO TRADE ANALYSIS", f"NO_ACTION events: {n:,}", ""]
    for r, c in vc.items():
        pct = 100.0 * float(c) / float(n) if n else 0.0
        lines.append(f"  {r}: {c:,} ({pct:.1f}%)")
    return "\n".join(lines) + "\n"
