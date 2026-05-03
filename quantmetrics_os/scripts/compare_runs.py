#!/usr/bin/env python3
"""Compare baseline vs candidate QuantLog JSONL runs."""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _fmt_num(value: float | None, digits: int = 2) -> str:
    if value is None:
        return "n/a"
    return f"{value:.{digits}f}"


def _fmt_pct(value: float | None, digits: int = 1) -> str:
    if value is None:
        return "n/a"
    return f"{value * 100:.{digits}f}%"


def _safe_div(numerator: float, denominator: float) -> float | None:
    if denominator == 0:
        return None
    return numerator / denominator


def _parse_ts(text: str | None) -> datetime | None:
    if not text:
        return None
    normalized = text.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            payload = line.strip()
            if not payload:
                continue
            rows.append(json.loads(payload))
    return rows


def _perf_metrics(events: list[dict[str, Any]]) -> dict[str, Any]:
    pnl_values: list[float] = []
    pnl_by_month: dict[str, list[float]] = defaultdict(list)
    for event in events:
        if event.get("event_type") != "trade_closed":
            continue
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        pnl_raw = payload.get("pnl_r")
        if not isinstance(pnl_raw, (int, float)):
            continue
        pnl = float(pnl_raw)
        pnl_values.append(pnl)
        ts = _parse_ts(event.get("timestamp_utc"))
        if ts is not None:
            pnl_by_month[f"{ts.year:04d}-{ts.month:02d}"].append(pnl)

    trade_count = len(pnl_values)
    expectancy = _safe_div(sum(pnl_values), trade_count) if trade_count else None
    gross_profit = sum(v for v in pnl_values if v > 0)
    gross_loss = abs(sum(v for v in pnl_values if v < 0))
    if gross_loss == 0:
        profit_factor = 999.99 if gross_profit > 0 else None
    else:
        profit_factor = gross_profit / gross_loss
    wins = sum(1 for v in pnl_values if v > 0)
    win_rate = _safe_div(wins, trade_count) if trade_count else None

    monthly_expectancy: dict[str, float] = {}
    for month, month_values in sorted(pnl_by_month.items()):
        monthly_expectancy[month] = sum(month_values) / len(month_values)

    return {
        "trade_count": trade_count,
        "expectancy_r": expectancy,
        "profit_factor": profit_factor,
        "win_rate": win_rate,
        "monthly_expectancy_r": monthly_expectancy,
    }


def _funnel_metrics(events: list[dict[str, Any]]) -> dict[str, Any]:
    counts = Counter(str(event.get("event_type", "")).strip() for event in events)
    signal_evaluated = int(counts.get("signal_evaluated", 0))

    action_events = 0
    enter_actions = 0
    no_action = 0
    for event in events:
        if event.get("event_type") != "trade_action":
            continue
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        action_events += 1
        decision = str(payload.get("decision", "")).upper().strip()
        if decision == "ENTER":
            enter_actions += 1
        if decision == "NO_ACTION":
            no_action += 1

    action_rate = _safe_div(enter_actions, signal_evaluated) if signal_evaluated else None
    no_action_rate = _safe_div(no_action, signal_evaluated) if signal_evaluated else None
    return {
        "signal_detected": int(counts.get("signal_detected", 0)),
        "signal_evaluated": signal_evaluated,
        "enter_actions": enter_actions,
        "no_action_events": no_action,
        "trade_action_events": action_events,
        "evaluated_to_action_rate": action_rate,
        "evaluated_to_no_action_rate": no_action_rate,
    }


def _guard_metrics(events: list[dict[str, Any]]) -> dict[str, Any]:
    guard_blocks: Counter[str] = Counter()
    for event in events:
        if event.get("event_type") != "risk_guard_decision":
            continue
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        decision = str(payload.get("decision", "")).upper().strip()
        if decision != "BLOCK":
            continue
        guard_name = str(payload.get("guard_name", "")).strip() or "UNKNOWN_GUARD"
        guard_blocks[guard_name] += 1

    total_blocks = int(sum(guard_blocks.values()))
    top_guard = None
    top_guard_count = 0
    top_guard_dominance = None
    if total_blocks > 0:
        top_guard, top_guard_count = guard_blocks.most_common(1)[0]
        top_guard_dominance = top_guard_count / total_blocks

    return {
        "total_blocks": total_blocks,
        "top_guard": top_guard,
        "top_guard_count": top_guard_count,
        "top_guard_dominance": top_guard_dominance,
        "guard_blocks": dict(guard_blocks.most_common()),
    }


def _monthly_consistency(
    baseline_monthly: dict[str, float], candidate_monthly: dict[str, float]
) -> dict[str, Any]:
    shared = sorted(set(baseline_monthly) & set(candidate_monthly))
    if not shared:
        return {
            "shared_months": [],
            "improved_months": 0,
            "deteriorated_months": 0,
            "consistency_ratio": None,
        }

    improved = 0
    deteriorated = 0
    for month in shared:
        if candidate_monthly[month] >= baseline_monthly[month]:
            improved += 1
        else:
            deteriorated += 1
    return {
        "shared_months": shared,
        "improved_months": improved,
        "deteriorated_months": deteriorated,
        "consistency_ratio": improved / len(shared),
    }


def _build_verdict(
    baseline: dict[str, Any],
    candidate: dict[str, Any],
    *,
    min_trades: int,
    max_guard_dominance: float,
) -> tuple[str, list[str]]:
    reasons: list[str] = []
    verdict = "PROMOTE"

    b_perf = baseline["performance"]
    c_perf = candidate["performance"]
    b_fun = baseline["funnel"]
    c_fun = candidate["funnel"]
    b_guard = baseline["guards"]
    c_guard = candidate["guards"]
    consistency = candidate["consistency_vs_baseline"]

    c_trades = int(c_perf.get("trade_count") or 0)
    if c_trades < min_trades:
        verdict = "REJECT"
        reasons.append(f"sample_size below gate ({c_trades} < {min_trades})")

    c_dom = c_guard.get("top_guard_dominance")
    if c_dom is not None and c_dom > max_guard_dominance:
        verdict = "REJECT"
        reasons.append(
            f"single guard dominates blocks ({_fmt_pct(c_dom)} > {_fmt_pct(max_guard_dominance)})"
        )

    cons_ratio = consistency.get("consistency_ratio")
    if cons_ratio is not None and cons_ratio < 0.60:
        verdict = "REJECT"
        reasons.append(
            f"improvement not consistent across shared months ({_fmt_pct(cons_ratio)} improved)"
        )

    b_exp = b_perf.get("expectancy_r")
    c_exp = c_perf.get("expectancy_r")
    exp_delta = (c_exp - b_exp) if (b_exp is not None and c_exp is not None) else None
    b_action = b_fun.get("evaluated_to_action_rate")
    c_action = c_fun.get("evaluated_to_action_rate")
    action_delta = (c_action - b_action) if (b_action is not None and c_action is not None) else None

    b_dom = b_guard.get("top_guard_dominance")
    c_dom = c_guard.get("top_guard_dominance")
    dom_delta = (c_dom - b_dom) if (b_dom is not None and c_dom is not None) else None

    if exp_delta is not None and exp_delta > 0:
        if action_delta is not None and abs(action_delta) >= 0.12:
            verdict = "REJECT"
            reasons.append(
                "expectancy gain likely explained by funnel shift (evaluated->action changed materially)"
            )
        if dom_delta is not None and dom_delta <= -0.20:
            verdict = "REJECT"
            reasons.append(
                "expectancy gain likely explained by reduced guard pressure, not cleaner signal quality"
            )

    if verdict == "PROMOTE":
        reasons.append("all hard compare gates passed")
    return verdict, reasons


def build_comparison(
    *,
    baseline_events: list[dict[str, Any]],
    candidate_events: list[dict[str, Any]],
    min_trades: int,
    max_guard_dominance: float,
) -> dict[str, Any]:
    baseline = {
        "performance": _perf_metrics(baseline_events),
        "funnel": _funnel_metrics(baseline_events),
        "guards": _guard_metrics(baseline_events),
    }
    candidate = {
        "performance": _perf_metrics(candidate_events),
        "funnel": _funnel_metrics(candidate_events),
        "guards": _guard_metrics(candidate_events),
    }

    consistency = _monthly_consistency(
        baseline["performance"]["monthly_expectancy_r"],
        candidate["performance"]["monthly_expectancy_r"],
    )
    candidate["consistency_vs_baseline"] = consistency

    verdict, reasons = _build_verdict(
        baseline,
        candidate,
        min_trades=min_trades,
        max_guard_dominance=max_guard_dominance,
    )

    return {
        "generated_at_utc": _now_utc(),
        "gates": {
            "min_trades": min_trades,
            "max_guard_dominance": max_guard_dominance,
            "min_consistency_ratio": 0.60,
        },
        "baseline": baseline,
        "candidate": candidate,
        "deltas": {
            "expectancy_r": (
                candidate["performance"]["expectancy_r"] - baseline["performance"]["expectancy_r"]
                if (
                    candidate["performance"]["expectancy_r"] is not None
                    and baseline["performance"]["expectancy_r"] is not None
                )
                else None
            ),
            "profit_factor": (
                candidate["performance"]["profit_factor"] - baseline["performance"]["profit_factor"]
                if (
                    candidate["performance"]["profit_factor"] is not None
                    and baseline["performance"]["profit_factor"] is not None
                )
                else None
            ),
            "win_rate": (
                candidate["performance"]["win_rate"] - baseline["performance"]["win_rate"]
                if (
                    candidate["performance"]["win_rate"] is not None
                    and baseline["performance"]["win_rate"] is not None
                )
                else None
            ),
            "evaluated_to_action_rate": (
                candidate["funnel"]["evaluated_to_action_rate"] - baseline["funnel"]["evaluated_to_action_rate"]
                if (
                    candidate["funnel"]["evaluated_to_action_rate"] is not None
                    and baseline["funnel"]["evaluated_to_action_rate"] is not None
                )
                else None
            ),
            "top_guard_dominance": (
                candidate["guards"]["top_guard_dominance"] - baseline["guards"]["top_guard_dominance"]
                if (
                    candidate["guards"]["top_guard_dominance"] is not None
                    and baseline["guards"]["top_guard_dominance"] is not None
                )
                else None
            ),
        },
        "verdict": verdict,
        "reasons": reasons,
    }


def render_markdown(result: dict[str, Any], *, baseline_label: str, candidate_label: str) -> str:
    b = result["baseline"]
    c = result["candidate"]
    d = result["deltas"]

    lines = [
        "# RUN COMPARISON",
        "",
        f"- Generated (UTC): {result.get('generated_at_utc')}",
        f"- Baseline: `{baseline_label}`",
        f"- Candidate: `{candidate_label}`",
        "",
        "## Performance",
        "",
        f"- expectancy: {_fmt_num(b['performance']['expectancy_r'])}R -> {_fmt_num(c['performance']['expectancy_r'])}R (delta {_fmt_num(d['expectancy_r'])}R)",
        f"- PF: {_fmt_num(b['performance']['profit_factor'])} -> {_fmt_num(c['performance']['profit_factor'])} (delta {_fmt_num(d['profit_factor'])})",
        f"- WR: {_fmt_pct(b['performance']['win_rate'])} -> {_fmt_pct(c['performance']['win_rate'])} (delta {_fmt_pct(d['win_rate'])})",
        f"- trades: {b['performance']['trade_count']} -> {c['performance']['trade_count']}",
        "",
        "## Funnel",
        "",
        f"- evaluated -> action: {_fmt_pct(b['funnel']['evaluated_to_action_rate'])} -> {_fmt_pct(c['funnel']['evaluated_to_action_rate'])}",
        f"- signal_evaluated: {b['funnel']['signal_evaluated']} -> {c['funnel']['signal_evaluated']}",
        f"- enter_actions: {b['funnel']['enter_actions']} -> {c['funnel']['enter_actions']}",
        "",
        "## Guards",
        "",
        f"- top block guard: `{b['guards']['top_guard']}` ({_fmt_pct(b['guards']['top_guard_dominance'])}) -> `{c['guards']['top_guard']}` ({_fmt_pct(c['guards']['top_guard_dominance'])})",
        f"- total blocks: {b['guards']['total_blocks']} -> {c['guards']['total_blocks']}",
        "",
        "## Time-slice consistency",
        "",
        f"- shared months: {len(c['consistency_vs_baseline']['shared_months'])}",
        f"- improved months: {c['consistency_vs_baseline']['improved_months']}",
        f"- consistency ratio: {_fmt_pct(c['consistency_vs_baseline']['consistency_ratio'])}",
        "",
        "## Verdict",
        "",
        f"**{result['verdict']}**",
        "",
    ]
    for reason in result.get("reasons", []):
        lines.append(f"- {reason}")
    lines.append("")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Compare two QuantLog event files")
    parser.add_argument("--baseline-jsonl", type=Path, required=True)
    parser.add_argument("--candidate-jsonl", type=Path, required=True)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("quantmetrics_os/runs/comparisons/baseline_vs_candidate_001"),
        help="Output directory for comparison artifacts (default under quantmetrics_os/runs/comparisons/).",
    )
    parser.add_argument("--baseline-label", default="baseline")
    parser.add_argument("--candidate-label", default="candidate")
    parser.add_argument("--min-trades", type=int, default=100)
    parser.add_argument("--max-guard-dominance", type=float, default=0.60)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    baseline_jsonl = args.baseline_jsonl.expanduser().resolve()
    candidate_jsonl = args.candidate_jsonl.expanduser().resolve()
    if not baseline_jsonl.is_file():
        raise FileNotFoundError(f"Baseline JSONL not found: {baseline_jsonl}")
    if not candidate_jsonl.is_file():
        raise FileNotFoundError(f"Candidate JSONL not found: {candidate_jsonl}")

    baseline_events = _read_jsonl(baseline_jsonl)
    candidate_events = _read_jsonl(candidate_jsonl)
    result = build_comparison(
        baseline_events=baseline_events,
        candidate_events=candidate_events,
        min_trades=int(args.min_trades),
        max_guard_dominance=float(args.max_guard_dominance),
    )

    out_dir = args.output_dir.expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    metrics_path = out_dir / "metrics.json"
    report_path = out_dir / "comparison_report.md"
    metrics_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    report_path.write_text(
        render_markdown(
            result,
            baseline_label=str(args.baseline_label),
            candidate_label=str(args.candidate_label),
        ),
        encoding="utf-8",
    )
    print(str(metrics_path))
    print(str(report_path))
    print(result["verdict"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
