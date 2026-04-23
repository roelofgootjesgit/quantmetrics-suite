"""Slice-based counterfactual estimation (MVP — level A)."""

from __future__ import annotations

from typing import Any

import pandas as pd

from quantmetrics_analytics.guard_attribution.normalize import norm_key


def slice_key_row(regime: Any, session: Any, setup_type: Any, signal_type: Any, signal_direction: Any) -> str:
    parts = (
        norm_key(regime),
        norm_key(session),
        norm_key(setup_type),
        norm_key(signal_type),
        norm_key(signal_direction),
    )
    return "|".join(parts)


def build_slice_statistics(executed: pd.DataFrame) -> tuple[dict[str, dict[str, Any]], pd.DataFrame]:
    """Mean ``pnl_r`` and sample size per slice; returns (stats dict, slice_df with key column)."""
    if executed.empty or "pnl_r" not in executed.columns:
        return {}, executed
    df = executed.dropna(subset=["pnl_r"]).copy()
    if df.empty:
        return {}, executed
    df["_slice_key"] = [
        slice_key_row(r["regime"], r["session"], r["setup_type"], r["signal_type"], r["signal_direction"])
        for _, r in df.iterrows()
    ]
    grp = df.groupby("_slice_key", dropna=False)
    agg = grp["pnl_r"].agg(["mean", "count"]).rename(columns={"mean": "mean_pnl_r", "count": "n"})
    stats: dict[str, dict[str, Any]] = {}
    for key, row in agg.iterrows():
        stats[str(key)] = {
            "mean_pnl_r": float(row["mean_pnl_r"]),
            "n": int(row["n"]),
        }
    return stats, df


def add_counterfactual_estimates(
    blocks: pd.DataFrame,
    slice_stats: dict[str, dict[str, Any]],
    *,
    min_slice_n: int,
    fallback_mean: float | None,
) -> pd.DataFrame:
    """Add ``estimated_r``, ``estimated_from_sample_n``, ``estimated_slice_key``, ``slice_has_data``."""
    if blocks.empty:
        return blocks
    out = blocks.copy()
    est_r: list[float | None] = []
    est_n: list[int] = []
    keys: list[str] = []
    fallback_used: list[bool] = []
    inconclusive_slice: list[bool] = []

    fm = fallback_mean if fallback_mean is not None else 0.0

    for _, r in out.iterrows():
        sk = slice_key_row(r.get("regime"), r.get("session"), r.get("setup_type"), r.get("signal_type"), r.get("signal_direction"))
        keys.append(sk)
        info = slice_stats.get(sk)
        if info is None:
            est_r.append(fm)
            est_n.append(0)
            fallback_used.append(True)
            inconclusive_slice.append(True)
            continue
        n = int(info["n"])
        mean_r = float(info["mean_pnl_r"])
        if n < min_slice_n:
            est_r.append(fm)
            est_n.append(n)
            fallback_used.append(True)
            inconclusive_slice.append(True)
            continue
        est_r.append(mean_r)
        est_n.append(n)
        fallback_used.append(False)
        inconclusive_slice.append(False)

    out["estimated_slice_key"] = keys
    out["estimated_r"] = est_r
    out["estimated_from_sample_n"] = est_n
    out["counterfactual_fallback"] = fallback_used
    out["counterfactual_inconclusive_small_sample"] = inconclusive_slice
    return out
