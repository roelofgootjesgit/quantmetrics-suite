"""End-to-end Guard Attribution MVP."""

from __future__ import annotations

import json
from typing import Any

import pandas as pd

from quantmetrics_analytics.guard_attribution.block_extractor import (
    extract_guard_blocks,
    join_blocks_with_signal_context,
    signal_evaluated_index,
)
from quantmetrics_analytics.guard_attribution.context_aggregator import aggregate_guard_context
from quantmetrics_analytics.guard_attribution.counterfactual import (
    add_counterfactual_estimates,
    build_slice_statistics,
)
from quantmetrics_analytics.guard_attribution.executed_slices import enrich_closed_with_signals, trade_closed_rows
from quantmetrics_analytics.guard_attribution.value_scorer import score_guards


def run_guard_attribution(
    events: list[dict[str, Any]],
    *,
    run_id: str,
    min_slice_n: int = 5,
) -> dict[str, Any]:
    """Passive attribution + slice counterfactuals for one ``run_id`` (events pre-filtered)."""
    sig_idx = signal_evaluated_index(events)
    blocks_raw = extract_guard_blocks(events)
    blocks_ctx = join_blocks_with_signal_context(blocks_raw, sig_idx)

    closed_raw = trade_closed_rows(events)
    executed = enrich_closed_with_signals(closed_raw, sig_idx)
    # executed needs signal_direction for slice key (from trade direction)
    if "signal_direction" not in executed.columns:
        executed["signal_direction"] = "unknown"

    slice_stats, slice_df = build_slice_statistics(executed)
    global_mean = 0.0
    if not executed.empty and executed["pnl_r"].notna().any():
        global_mean = float(executed["pnl_r"].mean())

    blocks_cf = add_counterfactual_estimates(
        blocks_ctx,
        slice_stats,
        min_slice_n=min_slice_n,
        fallback_mean=global_mean,
    )

    total_blocks = int(len(blocks_cf))
    ctx_summary = aggregate_guard_context(blocks_ctx)
    if total_blocks == 0:
        return {
            "meta": {
                "run_id": run_id,
                "min_slice_n": min_slice_n,
                "total_blocks": 0,
                "executed_trades": int(len(executed)),
                "slice_keys_with_data": len(slice_stats),
                "global_mean_pnl_r": round(global_mean, 6),
                "counterfactual_mode": "slice_mean_level_a",
            },
            "context_summary": ctx_summary,
            "guard_summary": {},
            "guard_score_table": [],
            "slice_preview": dict(list(slice_stats.items())[:40]),
            "blocks_detail": [],
        }

    score_table, guard_summary = score_guards(
        blocks_cf,
        total_blocks_run=total_blocks,
        min_slice_n=min_slice_n,
    )

    blocks_records = json.loads(blocks_cf.to_json(orient="records", date_format="iso"))

    return {
        "meta": {
            "run_id": run_id,
            "min_slice_n": min_slice_n,
            "total_blocks": total_blocks,
            "executed_trades": int(len(executed)),
            "slice_keys_with_data": len(slice_stats),
            "global_mean_pnl_r": round(global_mean, 6),
            "counterfactual_mode": "slice_mean_level_a",
        },
        "context_summary": ctx_summary,
        "guard_summary": guard_summary,
        "guard_score_table": score_table,
        "slice_preview": dict(list(slice_stats.items())[:40]),
        "blocks_detail": blocks_records[:5000],
    }
