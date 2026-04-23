"""Baseline vs variant comparison: JSON artifact + markdown."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from quantresearch.metrics_normalize import normalize_metrics
from quantresearch.paths import comparisons_dir, templates_dir


def _delta_numeric(a: float | int | None, b: float | int | None) -> float | int | None:
    if a is None or b is None:
        return None
    return b - a


COMPARE_KEYS = (
    "trade_count",
    "mean_r",
    "total_r",
    "winrate",
    "avg_win_r",
    "avg_loss_r",
    "profit_factor",
    "drawdown",
    "avg_mae_r",
    "avg_mfe_r",
    "mfe_capture_ratio",
    "signal_count",
    "enter_count",
    "no_action_count",
)


def compare_runs(
    baseline: dict[str, Any],
    variant: dict[str, Any],
    *,
    experiment_id: str,
    baseline_run_id: str = "",
    variant_run_id: str = "",
) -> dict[str, Any]:
    """
    Compare two metric dicts (raw or normalized). Returns comparison JSON with
    baseline, variant, delta, and automated decision hint.
    """
    b = normalize_metrics(baseline)
    v = normalize_metrics(variant)

    delta: dict[str, Any] = {}
    for k in COMPARE_KEYS:
        if k in b or k in v:
            bv = b.get(k)
            vv = v.get(k)
            d = _delta_numeric(
                float(bv) if bv is not None else None,
                float(vv) if vv is not None else None,
            )
            if d is not None:
                delta[k] = d

    from quantresearch.decision_engine import decide_comparison

    decision = decide_comparison(b, v, delta)

    return {
        "experiment_id": experiment_id,
        "baseline_run_id": baseline_run_id,
        "variant_run_id": variant_run_id,
        "baseline": {k: b[k] for k in COMPARE_KEYS if k in b},
        "variant": {k: v[k] for k in COMPARE_KEYS if k in v},
        "delta": delta,
        "decision": decision,
    }


def render_comparison_markdown(
    comparison: dict[str, Any],
    template_path: Path | None = None,
) -> str:
    tpl = template_path or (templates_dir() / "comparison_template.md")
    text = tpl.read_text(encoding="utf-8")

    exp_id = comparison.get("experiment_id", "")
    b = comparison.get("baseline", {})
    v = comparison.get("variant", {})
    d = comparison.get("delta", {})

    keys = sorted(set(b) | set(v))
    lines = ["| Metric | Baseline | Variant | Delta |", "|--------|----------|---------|-------|"]
    for k in keys:
        bv = b.get(k, "")
        vv = v.get(k, "")
        dv = d.get(k, "")
        lines.append(f"| {k} | {bv} | {vv} | {dv} |")
    summary_table = "\n".join(lines)

    delta_json = json.dumps(d, indent=2, ensure_ascii=False)

    out = (
        text.replace("{{experiment_id}}", str(exp_id))
        .replace("{{baseline_run_id}}", str(comparison.get("baseline_run_id", "")))
        .replace("{{variant_run_id}}", str(comparison.get("variant_run_id", "")))
        .replace("{{summary_table}}", summary_table)
        .replace("{{decision}}", str(comparison.get("decision", "")))
        .replace("{{delta_json}}", delta_json)
    )
    return out


def write_comparison_artifacts(
    comparison: dict[str, Any],
    *,
    out_dir: Path | None = None,
) -> tuple[Path, Path]:
    """Write EXP-XXX_comparison.json and .md under comparisons/."""
    base = out_dir or comparisons_dir()
    base.mkdir(parents=True, exist_ok=True)
    exp_id = comparison.get("experiment_id", "UNKNOWN")
    stem = f"{exp_id}_comparison"
    jp = base / f"{stem}.json"
    mp = base / f"{stem}.md"
    with open(jp, "w", encoding="utf-8") as f:
        json.dump(comparison, f, indent=2, ensure_ascii=False)
        f.write("\n")
    mp.write_text(render_comparison_markdown(comparison), encoding="utf-8")
    return jp, mp


def load_json_metrics(path: Path) -> dict[str, Any]:
    """Load metrics from a JSON file; supports top-level object or nested 'metrics' key."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data.get("metrics"), dict):
        return data["metrics"]
    return data
