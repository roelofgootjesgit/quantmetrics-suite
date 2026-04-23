"""Interpret priority insights from structured run summaries (warnings + key findings).

Turns diagnostic JSON blocks into actionable conclusions — not a replacement for data fixes upstream.
"""

from __future__ import annotations

import json
from typing import Any


# Thresholds (tunable)
_HIGH_CONTEXT_ABSENT_PCT = 50.0  # session/setup missing on majority of signal_evaluated
_MEDIUM_CONTEXT_ABSENT_PCT = 10.0
_GUARD_DOMINANCE_SHARE = 0.60  # single guard >= 60% of BLOCKs
_LIFECYCLE_GAP_FILL_RATIO = 0.80  # (fills - closes) / fills — suggests missing closes vs huge open book
_MIN_FILLS_FOR_LIFECYCLE_WARN = 50
_MISSING_DC_ROW_SHARE_HIGH = 0.15  # chain rows missing decision_cycle_id vs total DF rows


def _warn(level: str, code: str, detail: str) -> dict[str, Any]:
    return {"level": level, "code": code, "detail": detail}


def build_analytics_warnings(summary: dict[str, Any]) -> list[dict[str, Any]]:
    """Rule-based WARNINGS (HIGH / MEDIUM / LOW) from merged ``build_run_summary`` output."""
    out: list[dict[str, Any]] = []

    dq = summary.get("data_quality") or {}
    sf = summary.get("signal_funnel") or {}
    ctx = summary.get("context_completeness") or {}
    life = summary.get("lifecycle_status") or {}
    gd = summary.get("guard_diagnostics") or {}
    totals = summary.get("totals") or {}
    n_rows = int(totals.get("dataframe_rows", 0) or 0)

    # Funnel: evaluated > detected (impossible 1:1 story — retention > 100%)
    pct_eval = sf.get("pct_retained:signal_detected_to_signal_evaluated")
    if isinstance(pct_eval, (int, float)) and pct_eval > 100.01:
        out.append(
            _warn(
                "HIGH",
                "FUNNEL_EVAL_EXCEEDS_DETECT",
                f"signal_evaluated vs signal_detected implies {pct_eval:.1f}% 'retention' (>100%). "
                "Review duplicate emits, missing signal_detected, or multi-eval per detect.",
            )
        )
    for msg in dq.get("anomalies") or []:
        if "signal_evaluated_count_gt_signal_detected" in str(msg):
            out.append(_warn("HIGH", "FUNNEL_ORDERING", str(msg)))

    # decision_cycle_id coverage (global row share)
    missing_dc = int(dq.get("missing_decision_cycle_id_on_chain_rows", 0) or 0)
    if n_rows > 0 and missing_dc / float(n_rows) >= _MISSING_DC_ROW_SHARE_HIGH:
        out.append(
            _warn(
                "HIGH",
                "DECISION_CYCLE_ID_SPARSE",
                f"missing_decision_cycle_id on {missing_dc:,} chain rows ({100.0 * missing_dc / n_rows:.1f}% of all rows). "
                "Correlation and funnel-by-cycle are unreliable.",
            )
        )

    # Context completeness on signal_evaluated
    for field in ("session", "setup_type", "regime"):
        block = ctx.get(field)
        if not isinstance(block, dict):
            continue
        p = block.get("present_pct")
        if p is None:
            continue
        try:
            pv = float(p)
        except (TypeError, ValueError):
            continue
        if pv < _HIGH_CONTEXT_ABSENT_PCT:
            out.append(
                _warn(
                    "HIGH",
                    f"CONTEXT_{field.upper()}_MISSING",
                    f"payload_{field} present on only {pv:.1f}% of signal_evaluated rows.",
                )
            )
        elif pv < 100.0 - _MEDIUM_CONTEXT_ABSENT_PCT:
            out.append(
                _warn(
                    "MEDIUM",
                    f"CONTEXT_{field.upper()}_INCOMPLETE",
                    f"payload_{field} present on {pv:.1f}% of signal_evaluated rows.",
                )
            )

    # Lifecycle: many fills, few closes
    fills = int(life.get("order_filled_events", 0) or 0)
    gap = int(life.get("filled_minus_closed", 0) or 0)
    if fills >= _MIN_FILLS_FOR_LIFECYCLE_WARN and fills > 0:
        ratio = gap / float(fills)
        if ratio >= _LIFECYCLE_GAP_FILL_RATIO:
            out.append(
                _warn(
                    "HIGH",
                    "LIFECYCLE_CLOSE_GAP",
                    f"order_filled={fills:,}, trade_closed={int(life.get('trade_closed_events', 0) or 0):,}, "
                    f"filled_minus_closed={gap:,} (~{100.0 * ratio:.0f}% of fills without matching close event). "
                    "Check trade_closed logging, open positions, or ID correlation.",
                )
            )

    # Guard concentration
    total_b = int(gd.get("blocks_total", 0) or 0)
    by_g = gd.get("blocks_by_guard_name") or {}
    if total_b > 0 and isinstance(by_g, dict) and by_g:
        top_name = max(by_g, key=lambda k: by_g[k])
        top_n = int(by_g[top_name])
        share = top_n / float(total_b)
        if share >= _GUARD_DOMINANCE_SHARE:
            out.append(
                _warn(
                    "MEDIUM",
                    "GUARD_DOMINANCE",
                    f"{top_name!r} accounts for {100.0 * share:.0f}% of BLOCK decisions ({top_n:,}/{total_b:,}). "
                    "Risk lockdown may dominate throughput.",
                )
            )

    # De-dupe by code keeping highest severity (simple: first wins order HIGH first — insert order)
    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    for w in sorted(out, key=lambda x: order.get(str(x.get("level")), 9)):
        code = str(w.get("code", ""))
        if code in seen:
            continue
        seen.add(code)
        deduped.append(w)
    return deduped


def build_key_findings(summary: dict[str, Any]) -> dict[str, Any]:
    """Short prioritized narrative bullets derived from summary blocks."""
    problems: list[str] = []
    edges: list[str] = []
    blockers: list[str] = []
    system_state: list[str] = []

    dq = summary.get("data_quality") or {}
    anomalies = dq.get("anomalies") or []
    for a in anomalies[:5]:
        problems.append(str(a))

    ctx = summary.get("context_completeness") or {}
    for field in ("session", "setup_type", "regime"):
        b = ctx.get(field)
        if isinstance(b, dict) and b.get("present_pct") is not None:
            problems.append(
                f"{field}: present on {b['present_pct']}% of signal_evaluated rows "
                f"({ctx.get('rows', '?')} rows)"
            )

    md = int(dq.get("missing_decision_cycle_id_on_chain_rows", 0) or 0)
    if md > 0:
        problems.append(f"missing decision_cycle_id on {md:,} chain rows (correlation / cycle analytics degraded)")

    exp = summary.get("expectancy_slices") or {}
    by_reg = exp.get("by_regime_on_close") or {}
    if isinstance(by_reg, dict) and by_reg:
        ranked = sorted(
            by_reg.items(),
            key=lambda kv: (kv[1].get("mean_r", 0) if isinstance(kv[1], dict) else 0),
            reverse=True,
        )
        for name, row in ranked[:3]:
            if isinstance(row, dict) and row.get("n", 0) > 0:
                edges.append(
                    f"{name}: mean_r={row.get('mean_r', 0):.3f} (n={row.get('n', 0)})"
                )

    gd = summary.get("guard_diagnostics") or {}
    by_g = gd.get("blocks_by_guard_name") or {}
    total_b = int(gd.get("blocks_total", 0) or 0)
    if isinstance(by_g, dict) and by_g and total_b > 0:
        ranked_g = sorted(by_g.items(), key=lambda kv: kv[1], reverse=True)
        for name, n in ranked_g[:3]:
            pct = 100.0 * int(n) / float(total_b)
            blockers.append(f"{name}: {int(n):,} BLOCKs ({pct:.0f}% of guard blocks)")

    exp_overall = exp.get("overall") or {}
    if isinstance(exp_overall, dict) and exp_overall.get("n"):
        system_state.append(
            f"Closed-trade expectancy (overall): mean_r={exp_overall.get('mean_r', 0):.3f} over n={exp_overall.get('n', 0)}"
        )

    exit_e = summary.get("exit_efficiency") or {}
    med_cap = exit_e.get("median_capture_ratio_abs_r_over_abs_mfe")
    if med_cap is not None:
        system_state.append(f"Exit efficiency (median capture vs |MFE|): ~{100.0 * float(med_cap):.0f}%")

    sf = summary.get("signal_funnel") or {}
    if sf.get("signal_detected") is not None:
        system_state.append(
            f"Raw funnel counts: detected={sf.get('signal_detected')}, evaluated={sf.get('signal_evaluated')}, "
            f"ENTER/REVERSE={sf.get('trade_action_enter_reverse')}"
        )

    headline_parts: list[str] = []
    if problems:
        headline_parts.append("data/context integrity issues dominate interpretation")
    if blockers:
        headline_parts.append("guards heavily shape flow")
    if edges:
        headline_parts.append("regime expectancy differs materially")
    headline = "; ".join(headline_parts) if headline_parts else "Review extended blocks for detail."

    return {
        "headline": headline,
        "top_problems": problems[:8],
        "top_edges": edges[:5],
        "top_blockers": blockers[:5],
        "system_state": system_state[:6],
    }


def build_priority_layer(summary: dict[str, Any]) -> dict[str, Any]:
    """Warnings + key_findings for merging into ``build_run_summary``."""
    return {
        "analytics_warnings": build_analytics_warnings(summary),
        "key_findings": build_key_findings(summary),
    }


def format_key_findings_markdown(summary: dict[str, Any]) -> str:
    """Deterministic Markdown artefact (operator-facing). Stable section order; warnings sorted by severity then code."""
    lines: list[str] = []
    gen = str(summary.get("generated_at_utc", "")).strip()
    lines.append("# Key findings")
    lines.append("")
    if gen:
        lines.append(f"Generated (UTC): **{gen}**")
        lines.append("")

    aw = list(summary.get("analytics_warnings") or [])
    level_rank = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    aw.sort(key=lambda w: (level_rank.get(str(w.get("level", "")).upper(), 9), str(w.get("code", ""))))

    lines.append("## Warnings")
    lines.append("")
    if not aw:
        lines.append("*(none — no rule-based triggers fired for this run)*")
        lines.append("")
    else:
        lines.append("| Level | Code | Detail |")
        lines.append("| --- | --- | --- |")
        for w in aw:
            lvl = str(w.get("level", "")).replace("|", "\\|")
            code = str(w.get("code", "")).replace("|", "\\|")
            det = str(w.get("detail", "")).replace("|", "\\|").replace("\n", " ")
            lines.append(f"| {lvl} | `{code}` | {det} |")
        lines.append("")

    kf = summary.get("key_findings") or {}
    lines.append("## Headline")
    lines.append("")
    lines.append(str(kf.get("headline", "")).strip() or "*(none)*")
    lines.append("")

    def _bullets(title: str, key: str) -> None:
        items = kf.get(key) or []
        lines.append(f"## {title}")
        lines.append("")
        if not items:
            lines.append("*(none)*")
        else:
            for item in items:
                lines.append(f"- {item}")
        lines.append("")

    _bullets("Top problems", "top_problems")
    _bullets("Top edges", "top_edges")
    _bullets("Top blockers", "top_blockers")
    _bullets("System state", "system_state")

    lines.append("---")
    lines.append("")
    lines.append(
        "*Rule-based output only — same inputs yield the same Markdown. "
        "Fix upstream logging when HIGH warnings persist.*"
    )
    lines.append("")
    return "\n".join(lines)


def format_priority_for_research(summary: dict[str, Any]) -> str:
    """Readable preamble for CLI ``research`` output (prepended before JSON diagnostic blocks)."""
    parts: list[str] = []
    kf = summary.get("key_findings")
    if kf:
        parts.extend(["=== KEY FINDINGS ===", "", json.dumps(kf, indent=2, ensure_ascii=False), ""])
    aw = summary.get("analytics_warnings")
    if aw:
        parts.extend(["=== ANALYTICS WARNINGS ===", "", json.dumps(aw, indent=2, ensure_ascii=False), ""])
    if not parts:
        return ""
    return "\n".join(parts).rstrip() + "\n\n"
