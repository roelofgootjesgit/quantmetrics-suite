from __future__ import annotations

from pathlib import Path

from .models import DecisionCycle


def _fmt(value: float | int | None) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, int):
        return str(value)
    return f"{value:.4f}"


def generate_edge_report(
    run_id: str | None,
    source_events: str,
    events_count: int,
    cycles: list[DecisionCycle],
    guard_attribution: dict,
    stability: dict,
    decision_quality: list[dict],
    warnings: list[dict],
    edge_verdict: dict,
    throughput: dict | None,
    output_path: str,
) -> Path:
    out_file = Path(output_path)
    completed_cycles = sum(1 for c in cycles if not c.incomplete)
    incomplete_cycles = len(cycles) - completed_cycles
    trade_pnls = [c.pnl_r for c in cycles if c.trade_closed and c.pnl_r is not None]
    pnl_values = [float(v) for v in trade_pnls]
    win_rate = (sum(1 for x in pnl_values if x > 0) / len(pnl_values)) if pnl_values else None

    positive = sum(x for x in pnl_values if x > 0)
    negative = abs(sum(x for x in pnl_values if x < 0))
    profit_factor = None if not pnl_values else (float("inf") if negative == 0 else positive / negative)
    expectancy = (sum(pnl_values) / len(pnl_values)) if pnl_values else None

    lines: list[str] = [
        "# EDGE REPORT",
        "",
        "## 1. Run Summary",
        "",
        f"- Run ID: {run_id or 'n/a'}",
        f"- Source events: {source_events}",
        f"- Total events: {events_count}",
        f"- Total decision cycles: {len(cycles)}",
        f"- Completed cycles: {completed_cycles}",
        f"- Incomplete cycles: {incomplete_cycles}",
        f"- Output path: {out_file.parent}",
        "",
        "## 2. Performance Summary",
        "",
        f"- Total trades: {len(pnl_values)}",
        f"- Expectancy R: {_fmt(expectancy)}",
        f"- Win rate: {_fmt(win_rate)}",
        f"- Profit factor: {_fmt(profit_factor)}",
        f"- Max drawdown R: {_fmt(max((row.get('max_drawdown_r') or 0.0) for row in stability.get('regime', []) if row.get('max_drawdown_r') is not None) if stability.get('regime') else None)}",
        "",
    ]

    if throughput:
        lines.extend(
            [
                "## 3. Throughput Funnel (Diagnostics)",
                "",
                f"- raw_signals_detected: {throughput.get('raw_signals_detected')}",
                f"- signals_after_filters: {throughput.get('signals_after_filters')}",
                f"- signals_executed: {throughput.get('signals_executed')}",
                f"- filter_kill_ratio: {_fmt(throughput.get('filter_kill_ratio'))}",
                f"- execution_ratio: {_fmt(throughput.get('execution_ratio'))}",
                f"- trades_per_month: {_fmt(throughput.get('throughput_rates', {}).get('trades_per_month'))}",
                "",
                "### Top guard blocks (events)",
                "",
                "| Guard | Blocks |",
                "|---|---:|",
            ]
        )
        guard_blocks = throughput.get("breakdowns", {}).get("guard_blocks", {})
        top_blocks = sorted(guard_blocks.items(), key=lambda item: item[1], reverse=True)[:12]
        if top_blocks:
            for guard, count in top_blocks:
                lines.append(f"| {guard} | {count} |")
        else:
            lines.append("| n/a | 0 |")

        lines.extend(
            [
                "",
                "### Top filter reasons (signal_filtered)",
                "",
                "| Reason | Count |",
                "|---|---:|",
            ]
        )
        reasons = throughput.get("breakdowns", {}).get("filter_reasons", {})
        top_reasons = sorted(reasons.items(), key=lambda item: item[1], reverse=True)[:12]
        if top_reasons:
            for reason, count in top_reasons:
                lines.append(f"| {reason} | {count} |")
        else:
            lines.append("| n/a | 0 |")

        lines.extend(
            [
                "",
                "### Regime × guard blocks (top)",
                "",
                "| Regime | Guard | Blocks |",
                "|---|---|---:|",
            ]
        )
        regime_blocks = throughput.get("breakdowns", {}).get("regime_guard_blocks", {})
        top_regime = sorted(regime_blocks.items(), key=lambda item: item[1], reverse=True)[:12]
        if top_regime:
            for key, count in top_regime:
                regime, guard = (key.split(":", 1) + [""])[:2]
                lines.append(f"| {regime} | {guard} | {count} |")
        else:
            lines.append("| n/a | n/a | 0 |")

        lines.extend(
            [
                "",
                "### Session × guard blocks (top)",
                "",
                "| Session | Guard | Blocks |",
                "|---|---|---:|",
            ]
        )
        session_blocks = throughput.get("breakdowns", {}).get("session_guard_blocks", {})
        top_session = sorted(session_blocks.items(), key=lambda item: item[1], reverse=True)[:12]
        if top_session:
            for key, count in top_session:
                session, guard = (key.split(":", 1) + [""])[:2]
                lines.append(f"| {session} | {guard} | {count} |")
        else:
            lines.append("| n/a | n/a | 0 |")
        lines.append("")

    lines.extend(
        [
            "## 4. Guard Attribution",
            "",
            "| Guard | Blocks | Allows | Trades | Expectancy R | PF | Verdict |",
            "|---|---:|---:|---:|---:|---:|---|",
        ]
    )
    for row in guard_attribution.get("guards", []):
        lines.append(
            f"| {row.get('guard_name')} | {row.get('blocked_count')} | {row.get('allowed_count')} | "
            f"{row.get('closed_trades')} | {_fmt(row.get('expectancy_r'))} | {_fmt(row.get('profit_factor'))} | "
            f"{row.get('verdict')} |"
        )

    lines.extend(
        [
            "",
            "## 5. Regime Breakdown",
            "",
            "| Regime | Trades | Expectancy R | PF | Sample | Verdict |",
            "|---|---:|---:|---:|---|---|",
        ]
    )
    for row in stability.get("regime", []):
        lines.append(
            f"| {row.get('regime')} | {row.get('trade_count')} | {_fmt(row.get('expectancy_r'))} | "
            f"{_fmt(row.get('profit_factor'))} | {row.get('sample_quality')} | {row.get('verdict')} |"
        )

    lines.extend(
        [
            "",
            "## 6. Session Breakdown",
            "",
            "| Session | Trades | Expectancy R | PF | Sample | Verdict |",
            "|---|---:|---:|---:|---|---|",
        ]
    )
    for row in stability.get("session", []):
        lines.append(
            f"| {row.get('session')} | {row.get('trade_count')} | {_fmt(row.get('expectancy_r'))} | "
            f"{_fmt(row.get('profit_factor'))} | {row.get('sample_quality')} | {row.get('verdict')} |"
        )

    quality_counts = {
        "HIGH_QUALITY": 0,
        "MEDIUM_QUALITY": 0,
        "LOW_QUALITY": 0,
        "UNKNOWN": 0,
    }
    for row in decision_quality:
        quality_counts[row["quality_label"]] = quality_counts.get(row["quality_label"], 0) + 1

    lines.extend(
        [
            "",
            "## 7. Decision Quality",
            "",
            f"- High quality cycles: {quality_counts['HIGH_QUALITY']}",
            f"- Medium quality cycles: {quality_counts['MEDIUM_QUALITY']}",
            f"- Low quality cycles: {quality_counts['LOW_QUALITY']}",
            f"- Unknown cycles: {quality_counts['UNKNOWN']}",
            "",
            "## 8. Warnings",
            "",
        ]
    )
    if warnings:
        for warning in warnings:
            lines.append(f"- {warning.get('code')}: {warning}")
    else:
        lines.append("- None")

    lines.extend(
        [
            "",
            "## 9. Final Verdict",
            "",
            f"- Edge verdict: {edge_verdict.get('edge_verdict')}",
            f"- Confidence: {edge_verdict.get('confidence')}",
            f"- Main strength: {edge_verdict.get('main_strength')}",
            f"- Main risk: {edge_verdict.get('main_risk')}",
            f"- Recommended next action: {edge_verdict.get('recommended_next_action')}",
        ]
    )

    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out_file

