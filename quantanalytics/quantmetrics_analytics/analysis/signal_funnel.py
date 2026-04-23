"""Sprint 3: signal pipeline funnel (event counts + drop-off)."""

from __future__ import annotations

from typing import Any

import pandas as pd

from quantmetrics_analytics.analysis.extended_diagnostics import _quantbuild_subset

_FUNNEL_EVENT_TYPES: tuple[str, ...] = (
    "signal_detected",
    "signal_evaluated",
    "risk_guard_decision",
    "trade_action",
)


def _funnel_scope_df(df: pd.DataFrame) -> pd.DataFrame:
    """QuantBuild-only when ``source_system`` is present (SPRINT 3); else full frame."""
    if df.empty or "source_system" not in df.columns:
        return df
    qb = _quantbuild_subset(df)
    return qb if not qb.empty else df


def _count_type(df: pd.DataFrame, event_type: str) -> int:
    if df.empty or "event_type" not in df.columns:
        return 0
    return int((df["event_type"] == event_type).sum())


def _risk_allow_count(df: pd.DataFrame) -> int:
    if df.empty or "event_type" not in df.columns:
        return 0
    m = df["event_type"] == "risk_guard_decision"
    sub = df.loc[m]
    if sub.empty:
        return 0
    if "payload_decision" not in sub.columns:
        return len(sub)
    d = sub["payload_decision"].astype(str).str.strip().str.upper()
    return int((d == "ALLOW").sum())


def _trade_intent_count(df: pd.DataFrame) -> int:
    """ENTER or REVERSE trade_action decisions."""
    if df.empty or "event_type" not in df.columns:
        return 0
    m = df["event_type"] == "trade_action"
    sub = df.loc[m]
    if sub.empty or "payload_decision" not in sub.columns:
        return 0
    d = sub["payload_decision"].astype(str).str.strip().str.upper()
    return int(d.isin({"ENTER", "REVERSE"}).sum())


def signal_funnel_metrics_dict(df: pd.DataFrame) -> dict[str, Any]:
    """JSON-serializable funnel counts + stage-to-stage retention (%)."""
    wdf = _funnel_scope_df(df)
    detected = _count_type(wdf, "signal_detected")
    evaluated = _count_type(wdf, "signal_evaluated")
    risk_allowed = _risk_allow_count(wdf)
    trades = _trade_intent_count(wdf)

    stages: list[tuple[str, int]] = [
        ("signal_detected", detected),
        ("signal_evaluated", evaluated),
        ("risk_guard_decision_allow", risk_allowed),
        ("trade_action_enter_reverse", trades),
    ]
    out: dict[str, Any] = {
        "signal_detected": detected,
        "signal_evaluated": evaluated,
        "risk_guard_decision_allow": risk_allowed,
        "trade_action_enter_reverse": trades,
    }
    for i in range(len(stages) - 1):
        a, b = stages[i][1], stages[i + 1][1]
        label = f"pct_retained:{stages[i][0]}_to_{stages[i + 1][0]}"
        retained = 100.0 * float(b) / float(a) if a else 0.0
        out[label] = round(retained, 2)
    missing = [et for et in _FUNNEL_EVENT_TYPES if _count_type(wdf, et) == 0]
    if missing:
        out["zero_count_event_types"] = ", ".join(missing)
    return out


def format_signal_funnel(df: pd.DataFrame) -> str:
    lines = [
        "SIGNAL FUNNEL",
        "(QuantBuild rows only when source_system is present; same trace may emit multiple events)",
        "",
    ]
    wdf = _funnel_scope_df(df)
    detected = _count_type(wdf, "signal_detected")
    evaluated = _count_type(wdf, "signal_evaluated")
    risk_allowed = _risk_allow_count(wdf)
    trades = _trade_intent_count(wdf)

    stages: list[tuple[str, int]] = [
        ("signal_detected", detected),
        ("signal_evaluated", evaluated),
        ("risk_guard_decision (ALLOW only)", risk_allowed),
        ("trade_action (ENTER/REVERSE)", trades),
    ]
    for label, val in stages:
        lines.append(f"  {label}: {val:,}")
    lines.append("")

    for i in range(len(stages) - 1):
        a, b = stages[i][1], stages[i + 1][1]
        retained = 100.0 * float(b) / float(a) if a else 0.0
        drop = 100.0 - retained if a else 0.0
        lines.append(
            f"  {stages[i][0]} -> {stages[i + 1][0]}: "
            f"{retained:.1f}% retained ({drop:.1f}% drop)"
        )

    missing = [et for et in _FUNNEL_EVENT_TYPES if _count_type(wdf, et) == 0]
    if missing:
        lines.append("")
        lines.append(f"  Note: zero-count types: {', '.join(missing)}")
    return "\n".join(lines) + "\n"
