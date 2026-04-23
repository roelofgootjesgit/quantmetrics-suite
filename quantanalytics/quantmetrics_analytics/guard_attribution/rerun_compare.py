"""Level B — compare baseline vs variant QuantLog runs (guard-off reruns)."""

from __future__ import annotations

from typing import Any

from quantmetrics_analytics.guard_attribution.run_metrics import guard_block_counts, trade_performance_metrics


def _delta_metrics(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    """Variant (b) minus baseline (a) for numeric trade stats."""
    keys_float = ("mean_r", "sum_r", "winrate_pct", "max_dd_r", "profit_factor_like")
    keys_int = ("trade_count", "wins", "losses")
    out: dict[str, Any] = {}
    for k in keys_float:
        out[f"delta_{k}"] = round(float(b.get(k, 0)) - float(a.get(k, 0)), 6)
    for k in keys_int:
        out[f"delta_{k}"] = int(b.get(k, 0)) - int(a.get(k, 0))
    return out


def compare_guard_rerun_runs(
    events_baseline: list[dict[str, Any]],
    *,
    baseline_run_id: str,
    events_variant: list[dict[str, Any]],
    variant_run_id: str,
    baseline_label: str = "baseline",
    variant_label: str = "variant",
    guard_focus: str | None = None,
) -> dict[str, Any]:
    """Full comparison payload for reporting (two runs must be pre-filtered by ``run_id``)."""
    base = trade_performance_metrics(events_baseline)
    var = trade_performance_metrics(events_variant)
    blocks_base = guard_block_counts(events_baseline)
    blocks_var = guard_block_counts(events_variant)

    all_guards = sorted(set(blocks_base) | set(blocks_var))
    guard_rows = []
    for g in all_guards:
        cb = blocks_base.get(g, 0)
        cv = blocks_var.get(g, 0)
        row = {
            "guard_name": g,
            "blocks_baseline": cb,
            "blocks_variant": cv,
            "delta_blocks": cv - cb,
        }
        if guard_focus and g == guard_focus:
            row["focus_guard"] = True
        guard_rows.append(row)

    delta = _delta_metrics(base, var)

    interpretation: list[str] = []
    if delta["delta_trade_count"] != 0:
        interpretation.append(
            f"Variant adds {delta['delta_trade_count']:+d} trades vs baseline (realized outcomes)."
        )
    if delta["delta_mean_r"] != 0:
        interpretation.append(f"Mean R moves by {delta['delta_mean_r']:+.4f}.")
    if delta["delta_max_dd_r"] != 0:
        interpretation.append(f"Max DD (R path) moves by {delta['delta_max_dd_r']:+.4f}.")

    payload: dict[str, Any] = {
        "meta": {
            "comparison_mode": "level_b_guard_rerun",
            "baseline_label": baseline_label,
            "variant_label": variant_label,
            "baseline_run_id": baseline_run_id,
            "variant_run_id": variant_run_id,
            "guard_focus": guard_focus,
        },
        "baseline_metrics": base,
        "variant_metrics": var,
        "delta_trade_metrics": delta,
        "guard_blocks_baseline": blocks_base,
        "guard_blocks_variant": blocks_var,
        "guard_blocks_table": sorted(guard_rows, key=lambda r: (-abs(r["delta_blocks"]), r["guard_name"])),
        "interpretation_lines": interpretation,
    }

    if guard_focus:
        bf = blocks_base.get(guard_focus)
        vf = blocks_var.get(guard_focus)
        payload["guard_focus_summary"] = {
            "guard_name": guard_focus,
            "blocks_baseline": bf,
            "blocks_variant": vf,
            "delta_blocks": (vf or 0) - (bf or 0),
        }

    return payload
