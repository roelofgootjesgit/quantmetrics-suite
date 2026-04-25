#!/usr/bin/env python3
"""Hard promotion gate for QuantMetrics run analytics artifacts."""

from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _as_float(value: str | None) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _read_decision_quality(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        return [dict(row) for row in reader]


def _trade_metrics(decision_quality_rows: list[dict[str, str]]) -> dict[str, float | int | None]:
    pnl_values: list[float] = []
    for row in decision_quality_rows:
        pnl = _as_float(row.get("pnl_r"))
        if pnl is not None:
            pnl_values.append(pnl)

    total_trades = len(pnl_values)
    expectancy = (sum(pnl_values) / total_trades) if total_trades else None
    gross_profit = sum(v for v in pnl_values if v > 0)
    gross_loss = abs(sum(v for v in pnl_values if v < 0))
    if total_trades == 0:
        profit_factor = None
    elif gross_loss == 0:
        profit_factor = float("inf") if gross_profit > 0 else None
    else:
        profit_factor = gross_profit / gross_loss

    return {
        "total_trades": total_trades,
        "expectancy_r": expectancy,
        "profit_factor": profit_factor,
    }


def _has_protective_guard(guard_attribution: dict[str, Any]) -> bool:
    for row in guard_attribution.get("guards", []):
        if str(row.get("verdict", "")).upper() == "EDGE_PROTECTIVE":
            return True
    return False


def _major_warnings(warnings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    major: list[dict[str, Any]] = []
    for item in warnings:
        code = str(item.get("code", "")).strip()
        count = int(item.get("count", 1) or 1)
        if code and count > 0:
            major.append(item)
    return major


def _max_drawdown_r_from_stability(stability: dict[str, Any]) -> float | None:
    values: list[float] = []
    for _dimension, rows in stability.items():
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            dd = row.get("max_drawdown_r")
            if isinstance(dd, (int, float)):
                values.append(float(dd))
    if not values:
        return None
    return max(values)


def evaluate_promotion_gate(
    edge_verdict: dict[str, Any],
    guard_attribution: dict[str, Any],
    edge_stability: dict[str, Any],  # kept explicit as part of required inputs
    decision_quality_rows: list[dict[str, str]],
    warnings: list[dict[str, Any]],
    *,
    baseline_edge_stability: dict[str, Any] | None = None,
    max_dd_worsen_ratio: float | None = None,
) -> dict[str, Any]:
    metrics = _trade_metrics(decision_quality_rows)
    confidence = str(edge_verdict.get("confidence", "")).upper()
    protective_guard = _has_protective_guard(guard_attribution)
    major_warnings = _major_warnings(warnings)
    max_dd_r = _max_drawdown_r_from_stability(edge_stability)
    baseline_max_dd_r = (
        _max_drawdown_r_from_stability(baseline_edge_stability) if baseline_edge_stability is not None else None
    )

    checks: list[dict[str, Any]] = []

    def add_check(rule: str, passed: bool, fail_outcome: str, reason: str) -> None:
        checks.append(
            {
                "rule": rule,
                "passed": passed,
                "fail_outcome": fail_outcome,
                "reason": reason,
            }
        )

    add_check(
        "confidence must not be LOW",
        confidence != "LOW",
        "VALIDATION_REQUIRED",
        f"confidence={confidence or 'UNKNOWN'}",
    )
    add_check(
        "total_trades must be >= 100",
        int(metrics["total_trades"] or 0) >= 100,
        "VALIDATION_REQUIRED",
        f"total_trades={metrics['total_trades']}",
    )
    expectancy = metrics["expectancy_r"]
    add_check(
        "expectancy_R must be > 0",
        expectancy is not None and expectancy > 0,
        "REJECT",
        f"expectancy_R={expectancy}",
    )
    pf = metrics["profit_factor"]
    add_check(
        "profit_factor must be >= 1.25",
        pf is not None and pf >= 1.25,
        "REJECT",
        f"profit_factor={pf}",
    )
    add_check(
        "at least one protective guard required",
        protective_guard,
        "VALIDATION_REQUIRED",
        f"protective_guard_detected={protective_guard}",
    )
    add_check(
        "major warnings must be absent",
        len(major_warnings) == 0,
        "VALIDATION_REQUIRED",
        f"major_warnings={len(major_warnings)}",
    )

    if baseline_max_dd_r is not None and max_dd_r is not None and max_dd_worsen_ratio is not None:
        threshold = float(baseline_max_dd_r) * float(max_dd_worsen_ratio)
        add_check(
            "max_drawdown_R must not worsen materially vs baseline",
            float(max_dd_r) <= threshold,
            "VALIDATION_REQUIRED",
            f"max_dd_r={max_dd_r}, baseline_max_dd_r={baseline_max_dd_r}, threshold={threshold:.6f} (ratio={max_dd_worsen_ratio})",
        )

    reject_reasons = [c for c in checks if not c["passed"] and c["fail_outcome"] == "REJECT"]
    validation_reasons = [
        c for c in checks if not c["passed"] and c["fail_outcome"] == "VALIDATION_REQUIRED"
    ]

    if reject_reasons:
        final = "REJECT"
        failed = reject_reasons + validation_reasons
    elif validation_reasons:
        final = "VALIDATION_REQUIRED"
        failed = validation_reasons
    else:
        final = "PROMOTE"
        failed = []

    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "run_id": edge_verdict.get("run_id"),
        "promotion_decision": final,
        "all_rules_passed": len(failed) == 0,
        "metrics": metrics,
        "risk_shape": {
            "max_drawdown_r": max_dd_r,
            "baseline_max_drawdown_r": baseline_max_dd_r,
            "max_dd_worsen_ratio": max_dd_worsen_ratio,
        },
        "input_edge_verdict": edge_verdict.get("edge_verdict"),
        "input_confidence": edge_verdict.get("confidence"),
        "major_warning_count": len(major_warnings),
        "failed_rules": failed,
        "checks": checks,
        "reasons": [f"{item['rule']}: {item['reason']}" for item in failed],
    }


def _render_markdown(decision: dict[str, Any], analytics_dir: Path) -> str:
    lines = [
        "# PROMOTION DECISION",
        "",
        "## Decision",
        "",
        f"- Run ID: {decision.get('run_id')}",
        f"- Promotion decision: {decision.get('promotion_decision')}",
        f"- All rules passed: {decision.get('all_rules_passed')}",
        f"- Generated (UTC): {decision.get('generated_at_utc')}",
        "",
        "## Metrics Used",
        "",
        f"- Total trades: {decision['metrics'].get('total_trades')}",
        f"- Expectancy R: {decision['metrics'].get('expectancy_r')}",
        f"- Profit factor: {decision['metrics'].get('profit_factor')}",
        f"- Max drawdown R (stability peak): {decision.get('risk_shape', {}).get('max_drawdown_r')}",
        f"- Baseline max drawdown R: {decision.get('risk_shape', {}).get('baseline_max_drawdown_r')}",
        f"- Input edge verdict: {decision.get('input_edge_verdict')}",
        f"- Input confidence: {decision.get('input_confidence')}",
        f"- Major warning count: {decision.get('major_warning_count')}",
        "",
        "## Rule Checks",
        "",
        "| Rule | Passed | Fail outcome | Reason |",
        "|---|---|---|---|",
    ]
    for check in decision.get("checks", []):
        lines.append(
            f"| {check.get('rule')} | {check.get('passed')} | {check.get('fail_outcome')} | {check.get('reason')} |"
        )

    lines.extend(["", "## Reasons", ""])
    reasons = decision.get("reasons", [])
    if reasons:
        for reason in reasons:
            lines.append(f"- {reason}")
    else:
        lines.append("- All hard promotion rules passed.")

    lines.extend(
        [
            "",
            "## Input Artifacts",
            "",
            f"- {analytics_dir / 'edge_verdict.json'}",
            f"- {analytics_dir / 'guard_attribution.json'}",
            f"- {analytics_dir / 'edge_stability.json'}",
            f"- {analytics_dir / 'decision_quality.csv'}",
            f"- {analytics_dir / 'warnings.json'}",
        ]
    )

    return "\n".join(lines) + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Apply hard promotion gate to analytics artifacts")
    parser.add_argument(
        "--analytics-dir",
        type=Path,
        required=True,
        help="Path to run analytics folder containing edge_* and decision_quality outputs",
    )
    parser.add_argument(
        "--baseline-analytics-dir",
        type=Path,
        default=None,
        help="Optional baseline analytics folder for drawdown comparison (uses edge_stability.json)",
    )
    parser.add_argument(
        "--max-dd-worsen-ratio",
        type=float,
        default=None,
        help="If set with --baseline-analytics-dir, validates max drawdown does not worsen beyond ratio",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    analytics_dir = args.analytics_dir.expanduser().resolve()
    if not analytics_dir.is_dir():
        raise FileNotFoundError(f"Analytics directory not found: {analytics_dir}")

    edge_verdict = _load_json(analytics_dir / "edge_verdict.json")
    guard_attribution = _load_json(analytics_dir / "guard_attribution.json")
    edge_stability = _load_json(analytics_dir / "edge_stability.json")
    decision_quality_rows = _read_decision_quality(analytics_dir / "decision_quality.csv")
    warnings = _load_json(analytics_dir / "warnings.json")

    baseline_edge_stability = None
    if args.baseline_analytics_dir is not None:
        baseline_dir = args.baseline_analytics_dir.expanduser().resolve()
        baseline_edge_stability = _load_json(baseline_dir / "edge_stability.json")

    decision = evaluate_promotion_gate(
        edge_verdict=edge_verdict,
        guard_attribution=guard_attribution,
        edge_stability=edge_stability,
        decision_quality_rows=decision_quality_rows,
        warnings=warnings,
        baseline_edge_stability=baseline_edge_stability,
        max_dd_worsen_ratio=args.max_dd_worsen_ratio,
    )

    json_path = analytics_dir / "promotion_decision.json"
    md_path = analytics_dir / "PROMOTION_DECISION.md"
    json_path.write_text(json.dumps(decision, indent=2), encoding="utf-8")
    md_path.write_text(_render_markdown(decision, analytics_dir), encoding="utf-8")

    print(str(json_path))
    print(str(md_path))
    print(decision["promotion_decision"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

