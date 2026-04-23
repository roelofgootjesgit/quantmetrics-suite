"""Research-grade diagnostics (see quantmetrics_os docs/ANALYTICS_OUTPUT_GAPS.md)."""

from __future__ import annotations

import json
from collections import Counter
from typing import Any

import pandas as pd


def _safe_series(df: pd.DataFrame, col: str) -> pd.Series:
    if col not in df.columns:
        return pd.Series([], dtype=object)
    return df[col]


def _quantbuild_subset(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or "source_system" not in df.columns:
        return df
    return df[df["source_system"].astype(str).str.lower() == "quantbuild"]


def build_data_quality_report(df: pd.DataFrame) -> dict[str, Any]:
    """Event-count sanity checks, duplicate ids, rough orphan signals."""
    if df.empty:
        return {"note": "empty dataset"}

    et = _safe_series(df, "event_type").astype(str)
    counts = et.value_counts().to_dict()
    sd = int(counts.get("signal_detected", 0))
    se = int(counts.get("signal_evaluated", 0))
    ta = int(counts.get("trade_action", 0))
    ofl = int(counts.get("order_filled", 0))
    tcl = int(counts.get("trade_closed", 0))

    anomalies: list[str] = []
    # Funnel detect vs eval: compare QuantBuild rows only (SPRINT 3). Mixed stores often
    # attach non-QuantBuild signal_evaluated without QuantBuild signal_detected, which
    # inflates global ``se`` vs ``sd`` without indicating a QuantBuild emitter bug.
    qb_funnel = _quantbuild_subset(df)
    if not qb_funnel.empty:
        et_q = qb_funnel["event_type"].astype(str)
        c_q = et_q.value_counts().to_dict()
        sd_q = int(c_q.get("signal_detected", 0))
        se_q = int(c_q.get("signal_evaluated", 0))
        if se_q > sd_q and sd_q > 0:
            anomalies.append("signal_evaluated_count_gt_signal_detected (review ordering or missing detects)")
    elif se > sd and sd > 0:
        anomalies.append("signal_evaluated_count_gt_signal_detected (review ordering or missing detects)")
    if ofl > 0 and tcl > ofl:
        anomalies.append("trade_closed_gt_order_filled (unexpected; review lifecycle)")
    if ofl > 0 and tcl == 0:
        anomalies.append("order_filled_without_trade_closed (may be open at end of slice)")

    dcid = _safe_series(df, "decision_cycle_id")
    non_empty_dc = dcid.notna() & (dcid.astype(str).str.strip() != "")
    missing_dc_chain = int(((~non_empty_dc) & et.isin(["signal_detected", "signal_evaluated", "risk_guard_decision", "trade_action"])).sum())

    dup_dc_trade = 0
    if non_empty_dc.any() and "trade_action" in et.values:
        qb = et == "trade_action"
        sub = df.loc[qb & non_empty_dc, ["decision_cycle_id"]].copy()
        if not sub.empty:
            vc = sub["decision_cycle_id"].astype(str).value_counts()
            dup_dc_trade = int((vc > 1).sum())

    tid = _safe_series(df, "trade_id")
    non_empty_tid = tid.notna() & (tid.astype(str).str.strip() != "")
    duplicate_trade_id_envelopes = 0
    if non_empty_tid.any():
        vc = tid.astype(str).value_counts()
        duplicate_trade_id_envelopes = int((vc > 1).sum())

    return {
        "event_counts": {str(k): int(v) for k, v in counts.items()},
        "anomalies": anomalies,
        "missing_decision_cycle_id_on_chain_rows": missing_dc_chain,
        "duplicate_decision_cycle_ids_with_multiple_trade_action_rows": dup_dc_trade,
        "duplicate_trade_id_on_envelope": duplicate_trade_id_envelopes,
    }


def build_context_completeness(df: pd.DataFrame) -> dict[str, Any]:
    """Share of signal_evaluated rows with key payload fields (flattened columns)."""
    if df.empty:
        return {}
    ev = df[df["event_type"].astype(str) == "signal_evaluated"]
    if ev.empty:
        return {"note": "no signal_evaluated rows"}
    n = len(ev)
    fields = [
        "payload_session",
        "payload_regime",
        "payload_setup_type",
        "payload_signal_type",
        "payload_confidence",
    ]
    out: dict[str, Any] = {"rows": n}
    for f in fields:
        if f not in ev.columns:
            out[f.replace("payload_", "")] = {"present_pct": None, "note": "column_absent"}
            continue
        s = ev[f]
        ok = s.notna() & (s.astype(str).str.strip() != "") & (s.astype(str) != "<NA>")
        out[f.replace("payload_", "")] = {"present_pct": round(100.0 * float(ok.sum()) / float(n), 2)}
    return out


def build_lifecycle_status(df: pd.DataFrame) -> dict[str, Any]:
    """ENTER vs fills vs closes (envelope + payload trade_id where present)."""
    if df.empty:
        return {}
    et = df["event_type"].astype(str)
    enter = 0
    if "payload_decision" in df.columns:
        m = et == "trade_action"
        d = df.loc[m, "payload_decision"].astype(str).str.upper().str.strip()
        enter = int((d == "ENTER").sum())
    filled = int((et == "order_filled").sum())
    closed = int((et == "trade_closed").sum())
    os_filled = max(0, filled - closed)
    return {
        "trade_action_enter_rows": enter,
        "order_filled_events": filled,
        "trade_closed_events": closed,
        "filled_minus_closed": os_filled,
        "note": "filled_minus_closed approximates outstanding closes if 1:1 fill→close mapping",
    }


def build_guard_diagnostics(df: pd.DataFrame) -> dict[str, Any]:
    """BLOCK rows by guard_name; optional session/regime slice when columns exist."""
    if df.empty or "event_type" not in df.columns:
        return {}
    rg = df[df["event_type"].astype(str) == "risk_guard_decision"]
    if rg.empty:
        return {"note": "no risk_guard_decision events"}
    if "payload_decision" not in rg.columns or "payload_guard_name" not in rg.columns:
        return {"note": "missing payload_guard_name or payload_decision"}

    dec = rg["payload_decision"].astype(str).str.upper().str.strip()
    blocks = rg[dec == "BLOCK"]
    if blocks.empty:
        return {"blocks_total": 0}

    by_guard = blocks["payload_guard_name"].fillna("<missing>").astype(str).value_counts().to_dict()
    out: dict[str, Any] = {
        "blocks_total": int(len(blocks)),
        "blocks_by_guard_name": {str(k): int(v) for k, v in by_guard.items()},
    }
    if "payload_session" in blocks.columns:
        sub = (
            blocks.groupby([blocks["payload_guard_name"].fillna("<missing>").astype(str), blocks["payload_session"].fillna("<missing>").astype(str)])
            .size()
            .reset_index(name="n")
        )
        out["blocks_by_guard_and_session"] = sub.to_dict(orient="records")
    if "payload_regime" in blocks.columns:
        sub = (
            blocks.groupby([blocks["payload_guard_name"].fillna("<missing>").astype(str), blocks["payload_regime"].fillna("<missing>").astype(str)])
            .size()
            .reset_index(name="n")
        )
        out["blocks_by_guard_and_regime"] = sub.to_dict(orient="records")
    return out


def build_decision_cycle_funnel(df: pd.DataFrame) -> dict[str, Any]:
    """One row per decision_cycle_id (quantbuild envelope); terminal trade_action outcome."""
    if df.empty or "decision_cycle_id" not in df.columns:
        return {"note": "no decision_cycle_id column"}
    qb = _quantbuild_subset(df)
    if qb.empty:
        return {"note": "no quantbuild rows"}

    dc = qb["decision_cycle_id"].astype(str).str.strip()
    qb = qb.assign(_dc=dc)
    qb = qb[qb["_dc"] != ""]
    if qb.empty:
        return {"note": "no non-empty decision_cycle_id"}

    chain_types = {"signal_detected", "signal_evaluated", "risk_guard_decision", "trade_action"}
    terminal: dict[str, str] = {}

    def _terminal_decision(g: pd.DataFrame) -> str:
        ta = g[g["event_type"].astype(str) == "trade_action"]
        if ta.empty:
            return "<no_trade_action>"
        last = ta.sort_values(["timestamp_utc", "source_seq"], na_position="last").iloc[-1]
        pdv = last.get("payload_decision")
        return str(pdv).strip().upper() if pdv is not None else "<unknown>"

    cycles = qb["_dc"].unique()
    n_cycles = len(cycles)
    flags = {
        "has_signal_detected": 0,
        "has_signal_evaluated": 0,
        "has_risk_guard_decision": 0,
        "terminal_enter": 0,
        "terminal_no_action": 0,
        "terminal_other_or_missing": 0,
    }
    cycles_eval_without_detect = 0

    for cyc in cycles:
        g = qb[qb["_dc"] == cyc]
        et = set(g["event_type"].astype(str).unique())
        if "signal_detected" in et:
            flags["has_signal_detected"] += 1
        if "signal_evaluated" in et:
            flags["has_signal_evaluated"] += 1
        if "signal_evaluated" in et and "signal_detected" not in et:
            cycles_eval_without_detect += 1
        if "risk_guard_decision" in et:
            flags["has_risk_guard_decision"] += 1
        td = _terminal_decision(g)
        terminal[cyc] = td
        if td == "ENTER":
            flags["terminal_enter"] += 1
        elif td == "NO_ACTION":
            flags["terminal_no_action"] += 1
        else:
            flags["terminal_other_or_missing"] += 1

    qbet = qb["event_type"].astype(str)
    has_fill = (
        int(qb[qbet == "order_filled"]["_dc"].drop_duplicates().nunique())
        if (qbet == "order_filled").any()
        else 0
    )
    has_close = (
        int(qb[qbet == "trade_closed"]["_dc"].drop_duplicates().nunique())
        if (qbet == "trade_closed").any()
        else 0
    )

    mix = Counter(terminal.values())

    return {
        "unique_decision_cycles": n_cycles,
        "cycle_stage_presence": flags,
        "cycles_signal_evaluated_without_signal_detected": cycles_eval_without_detect,
        "cycles_with_order_filled": has_fill,
        "cycles_with_trade_closed": has_close,
        "terminal_trade_action_mix": {str(k): int(v) for k, v in mix.items()},
    }


def build_expectancy_slices(df: pd.DataFrame) -> dict[str, Any]:
    """Expectancy from trade_closed using payload_regime / payload_session when present."""
    if df.empty:
        return {}
    tc = df[df["event_type"].astype(str) == "trade_closed"]
    if tc.empty:
        return {"note": "no trade_closed"}

    col = None
    for c in ("payload_pnl_r", "payload_r_multiple"):
        if c in tc.columns:
            col = c
            break
    if col is None:
        return {"note": "trade_closed missing payload_pnl_r / payload_r_multiple"}

    v = pd.to_numeric(tc[col], errors="coerce")
    tc = tc.assign(_r=v)
    tc = tc[tc["_r"].notna()]
    if tc.empty:
        return {"note": "no numeric R column on trade_closed"}

    def _slice(group_col: str) -> dict[str, dict[str, float | int]]:
        if group_col not in tc.columns:
            return {}
        out: dict[str, dict[str, float | int]] = {}
        for name, grp in tc.groupby(tc[group_col].fillna("<missing>").astype(str)):
            s = grp["_r"]
            out[str(name)] = {"n": int(len(s)), "mean_r": float(s.mean()), "sum_r": float(s.sum())}
        return out

    return {
        "metric_column": col,
        "overall": {"n": int(len(tc)), "mean_r": float(tc["_r"].mean())},
        "by_regime_on_close": _slice("payload_regime"),
        "by_session_on_close": _slice("payload_session"),
    }


def build_exit_efficiency(df: pd.DataFrame) -> dict[str, Any]:
    """MAE/MFE vs realized R when columns exist on trade_closed."""
    if df.empty:
        return {}
    tc = df[df["event_type"].astype(str) == "trade_closed"]
    if tc.empty:
        return {"note": "no trade_closed"}

    need = ["payload_pnl_r", "payload_mae_r", "payload_mfe_r"]
    if not all(c in tc.columns for c in need):
        present = [c for c in need if c in tc.columns]
        return {"note": f"need payload_pnl_r, payload_mae_r, payload_mfe_r; have {present}"}

    r = pd.to_numeric(tc["payload_pnl_r"], errors="coerce")
    mae = pd.to_numeric(tc["payload_mae_r"], errors="coerce").abs()
    mfe = pd.to_numeric(tc["payload_mfe_r"], errors="coerce").abs()
    ok = r.notna() & mae.notna() & mfe.notna()
    if not ok.any():
        return {"note": "non-numeric mae/mfe/r"}

    cap = (r.abs() / mfe.replace(0, pd.NA)).clip(upper=10.0)
    cap_valid = cap.dropna()

    exit_reason = {}
    if "payload_exit" in tc.columns:
        exit_reason = tc["payload_exit"].fillna("<missing>").astype(str).value_counts().head(15).to_dict()

    return {
        "rows": int(ok.sum()),
        "avg_realized_r": float(r[ok].mean()),
        "avg_abs_mae_r": float(mae[ok].mean()),
        "avg_abs_mfe_r": float(mfe[ok].mean()),
        "median_capture_ratio_abs_r_over_abs_mfe": float(cap_valid.median()) if len(cap_valid) else None,
        "exit_tag_counts": {str(k): int(v) for k, v in exit_reason.items()},
    }


def build_extended_summary(events: list[dict[str, Any]], df: pd.DataFrame) -> dict[str, Any]:
    """Full extended diagnostics block for run_summary.json."""
    _ = events  # reserved for future raw-event checks
    return {
        "data_quality": build_data_quality_report(df),
        "decision_cycle_funnel": build_decision_cycle_funnel(df),
        "lifecycle_status": build_lifecycle_status(df),
        "context_completeness": build_context_completeness(df),
        "guard_diagnostics": build_guard_diagnostics(df),
        "expectancy_slices": build_expectancy_slices(df),
        "exit_efficiency": build_exit_efficiency(df),
    }


def format_extended_report_text(summary: dict[str, Any]) -> str:
    """Human-readable block for CLI ``research`` report."""
    from quantmetrics_analytics.analysis.priority_insights import format_priority_for_research

    preamble = format_priority_for_research(summary)

    keys = (
        "data_quality",
        "decision_cycle_funnel",
        "lifecycle_status",
        "context_completeness",
        "guard_diagnostics",
        "expectancy_slices",
        "exit_efficiency",
    )
    lines: list[str] = []
    if preamble.strip():
        lines.append(preamble.rstrip())
        lines.append("")
    lines.extend(["RESEARCH DIAGNOSTICS (ANALYTICS_OUTPUT_GAPS-style)", "", ""])
    for k in keys:
        block = summary.get(k)
        if block is None:
            continue
        title = k.replace("_", " ").upper()
        lines.append(f"=== {title} ===")
        lines.append("")
        lines.append(json.dumps(block, indent=2, ensure_ascii=False))
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"
