"""Structured run summary (JSON-serializable) for MVP dashboard / CI artefacts."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from quantmetrics_analytics.analysis.extended_diagnostics import build_extended_summary
from quantmetrics_analytics.analysis.priority_insights import build_priority_layer
from quantmetrics_analytics.analysis.no_trade_analysis import no_action_distribution_dict
from quantmetrics_analytics.analysis.signal_funnel import signal_funnel_metrics_dict


def _event_type_counts(df: pd.DataFrame) -> dict[str, int]:
    if df.empty or "event_type" not in df.columns:
        return {}
    vc = df["event_type"].astype(str).value_counts()
    return {str(k): int(v) for k, v in vc.items()}


def _expectancy_by_regime(df: pd.DataFrame) -> dict[str, Any]:
    """Mean R or pnl_r on ``trade_closed`` rows when numeric columns exist."""
    if df.empty or "event_type" not in df.columns:
        return {}
    tc = df[df["event_type"] == "trade_closed"]
    if tc.empty:
        return {"note": "no trade_closed events"}
    col = None
    for c in ("payload_r_multiple", "payload_pnl_r"):
        if c in tc.columns:
            col = c
            break
    if col is None:
        return {"note": "trade_closed without payload_r_multiple / payload_pnl_r"}

    vals = pd.to_numeric(tc[col], errors="coerce").dropna()
    if vals.empty:
        return {"note": f"{col} non-numeric or empty"}

    out: dict[str, Any] = {"overall": {"n": int(len(vals)), "mean": float(vals.mean())}}
    # Attach regime from same-row payload if logged on trade_closed
    if "payload_exit_reason" in tc.columns or "payload_regime" in tc.columns:
        reg_col = "payload_regime" if "payload_regime" in tc.columns else None
        if reg_col:
            g = tc.groupby(tc[reg_col].fillna("<missing>").astype(str), dropna=False)[col]
            out["by_regime_on_close_event"] = {}
            for name, ser in g:
                v = pd.to_numeric(ser, errors="coerce").dropna()
                if not v.empty:
                    out["by_regime_on_close_event"][str(name)] = {"n": int(len(v)), "mean": float(v.mean())}
    return out


def build_run_summary(
    *,
    events: list[dict[str, Any]],
    df: pd.DataFrame,
    input_paths: list[Path],
) -> dict[str, Any]:
    core: dict[str, Any] = {
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "inputs": {
            "paths_count": len(input_paths),
            "paths_sample": [str(p) for p in input_paths[:16]],
        },
        "totals": {"events_loaded": len(events), "dataframe_rows": len(df)},
        "event_type_counts": _event_type_counts(df),
        "signal_funnel": signal_funnel_metrics_dict(df),
        "no_action_distribution": no_action_distribution_dict(df),
        "expectancy": _expectancy_by_regime(df),
    }
    core.update(build_extended_summary(events, df))
    core.update(build_priority_layer(core))
    return core


def run_summary_to_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# Run summary",
        "",
        f"Generated: **{summary.get('generated_at_utc', '')}**",
        "",
    ]
    kf = summary.get("key_findings")
    if kf:
        lines.extend(["## Key findings (priority)", "", "```json"])
        lines.append(json.dumps(kf, indent=2, ensure_ascii=False))
        lines.extend(["```", ""])
    aw = summary.get("analytics_warnings")
    if aw:
        lines.extend(["## Analytics warnings", "", "```json"])
        lines.append(json.dumps(aw, indent=2, ensure_ascii=False))
        lines.extend(["```", ""])
    lines.extend(
        [
            "## Totals",
            "",
        ]
    )
    t = summary.get("totals") or {}
    lines.append(f"- Events loaded: {t.get('events_loaded', 0):,}")
    lines.append(f"- DataFrame rows: {t.get('dataframe_rows', 0):,}")
    lines.append("")
    lines.append("## Event types")
    lines.append("")
    for et, n in sorted((summary.get("event_type_counts") or {}).items(), key=lambda x: (-x[1], x[0])):
        lines.append(f"- `{et}`: {n:,}")
    lines.append("")
    sf = summary.get("signal_funnel") or {}
    lines.append("## Signal funnel")
    lines.append("")
    for k, v in sf.items():
        lines.append(f"- **{k}**: {v}")
    lines.append("")
    nad = summary.get("no_action_distribution") or {}
    lines.append("## NO_ACTION distribution")
    lines.append("")
    if not nad:
        lines.append("(none)")
    else:
        for r, row in nad.items():
            if isinstance(row, dict):
                lines.append(f"- {r}: {row.get('count', '')} ({row.get('pct_of_no_action', '')}%)")
            else:
                lines.append(f"- {r}: {row}")
    lines.append("")
    exp = summary.get("expectancy") or {}
    lines.append("## Expectancy (trade_closed)")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps(exp, indent=2, ensure_ascii=False))
    lines.append("```")
    lines.append("")
    for block_key, title in (
        ("data_quality", "Data quality"),
        ("decision_cycle_funnel", "Decision-cycle funnel"),
        ("lifecycle_status", "Lifecycle status"),
        ("context_completeness", "Context completeness"),
        ("guard_diagnostics", "Guard diagnostics"),
        ("expectancy_slices", "Expectancy slices"),
        ("exit_efficiency", "Exit efficiency"),
    ):
        blk = summary.get(block_key)
        if blk is None:
            continue
        lines.append(f"## {title}")
        lines.append("")
        lines.append("```json")
        lines.append(json.dumps(blk, indent=2, ensure_ascii=False))
        lines.append("```")
        lines.append("")
    return "\n".join(lines)
