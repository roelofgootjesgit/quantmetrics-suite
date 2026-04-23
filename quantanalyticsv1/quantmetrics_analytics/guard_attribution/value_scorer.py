"""Guard Value Scorer — net block value and coarse assessments."""

from __future__ import annotations

from typing import Any

import pandas as pd


def _safe_float(x: Any) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


def score_guards(
    blocks_with_cf: pd.DataFrame,
    *,
    total_blocks_run: int,
    min_slice_n: int,
    overblocking_share_threshold: float = 0.40,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Per-guard scorecard rows + dominance summary."""
    if blocks_with_cf.empty or total_blocks_run <= 0:
        return [], {}

    rows: list[dict[str, Any]] = []
    guard_names = blocks_with_cf["guard_name"].dropna().unique()

    dominant_guard: str | None = None
    dominant_share = 0.0
    largest_throughput: str | None = None
    largest_n = -1

    for g in sorted(str(x) for x in guard_names):
        sub = blocks_with_cf[blocks_with_cf["guard_name"] == g]
        n_block = len(sub)
        share = float(n_block) / float(total_blocks_run)
        if share > dominant_share:
            dominant_share = share
            dominant_guard = g
        if n_block > largest_n:
            largest_n = n_block
            largest_throughput = g

        er = sub["estimated_r"].map(_safe_float)
        missed_winners = int((er > 0).sum())
        avoided_losers = int((er < 0).sum())
        missed_winners_r = float(er.clip(lower=0).sum())
        avoided_losses_r = float((-er).clip(lower=0).sum())
        net_block_value_r = float(avoided_losses_r - missed_winners_r)
        mean_est = float(er.mean()) if len(er) else 0.0

        valid_slice_mask = ~sub["counterfactual_fallback"].astype(bool)
        n_valid_cf = int(valid_slice_mask.sum())

        assessment = _assess_guard(
            share=share,
            mean_estimated_r=mean_est,
            n_blocks=n_block,
            n_valid_counterfactual=n_valid_cf,
            min_slice_n=min_slice_n,
            overblocking_share_threshold=overblocking_share_threshold,
        )

        rows.append(
            {
                "guard_name": g,
                "blocks": n_block,
                "share_of_all_blocks": round(share, 4),
                "estimated_missed_winners_count": missed_winners,
                "estimated_avoided_losers_count": avoided_losers,
                "estimated_missed_winners_r": round(missed_winners_r, 4),
                "estimated_avoided_losses_r": round(avoided_losses_r, 4),
                "net_block_value_r": round(net_block_value_r, 4),
                "mean_estimated_r": round(mean_est, 6),
                "blocks_with_valid_slice_cf": n_valid_cf,
                "assessment": assessment,
            }
        )

    summary = {
        "most_dominant_guard": dominant_guard,
        "dominant_share": round(dominant_share, 4),
        "largest_throughput_guard": largest_throughput,
        "most_dominant_guard_share_pct": round(100.0 * dominant_share, 2),
    }

    likely_over = [r["guard_name"] for r in rows if r["assessment"] == "likely_overblocking"]
    summary["likely_overblocking_guards"] = likely_over

    return rows, summary


def _assess_guard(
    *,
    share: float,
    mean_estimated_r: float,
    n_blocks: int,
    n_valid_counterfactual: int,
    min_slice_n: int,
    overblocking_share_threshold: float,
) -> str:
    """First-pass labels; requires non-trivial sample for strong claims."""
    if n_blocks < 2:
        return "inconclusive_small_sample"
    if n_valid_counterfactual < max(2, min_slice_n // 2):
        return "inconclusive_small_sample"
    if mean_estimated_r < 0:
        return "likely_protective"
    if share > overblocking_share_threshold and mean_estimated_r > 0:
        return "likely_overblocking"
    return "inconclusive"
