"""Rule-based decisions for baseline vs variant (MVP rules from spec)."""

from __future__ import annotations

from typing import Any

# Thresholds (tunable constants for MVP)
MEAN_R_MATERIAL = 0.15
MIN_TRADE_COUNT_INCONCLUSIVE = 3


def decide_comparison(
    baseline: dict[str, Any],
    variant: dict[str, Any],
    delta: dict[str, Any],
) -> str:
    """
    First rule-based model:
    - mean_r clearly improves and trade_count not too low → variant_outperforms_baseline
    - winrate up AND MAE/MFE improve → variant_outperforms_baseline (or reinforce)
    - trade_count collapses near zero → inconclusive
    - mean_r worse → baseline_preferred / negative
    """
    btc = baseline.get("trade_count")
    vtc = variant.get("trade_count")
    bmr = baseline.get("mean_r")
    vmr = variant.get("mean_r")

    if isinstance(vtc, int) and vtc < MIN_TRADE_COUNT_INCONCLUSIVE:
        return "inconclusive_low_sample"

    if isinstance(btc, int) and isinstance(vtc, int):
        if vtc < max(2, btc // 10) and btc >= 10:
            return "inconclusive_trade_collapse"

    if bmr is not None and vmr is not None:
        dmr = float(vmr) - float(bmr)
        if dmr < -MEAN_R_MATERIAL:
            return "baseline_preferred"

        wr_b = baseline.get("winrate")
        wr_v = variant.get("winrate")
        mae_b = baseline.get("avg_mae_r")
        mae_v = variant.get("avg_mae_r")
        mfe_b = baseline.get("avg_mfe_r")
        mfe_v = variant.get("avg_mfe_r")

        quality_up = False
        if wr_b is not None and wr_v is not None and wr_v > wr_b:
            if mae_b is not None and mae_v is not None and mfe_b is not None and mfe_v is not None:
                if mae_v <= mae_b and mfe_v >= mfe_b:
                    quality_up = True

        if dmr >= MEAN_R_MATERIAL:
            if isinstance(vtc, int) and vtc >= MIN_TRADE_COUNT_INCONCLUSIVE:
                return "variant_outperforms_baseline"

        if quality_up and dmr >= 0:
            return "variant_outperforms_baseline"

        if dmr >= MEAN_R_MATERIAL:
            return "variant_outperforms_baseline"

    return "inconclusive_or_mixed"


def map_decision_to_experiment_result(decision: str) -> str:
    if decision in ("variant_outperforms_baseline",):
        return "positive"
    if decision in ("baseline_preferred",):
        return "negative"
    return "inconclusive"
