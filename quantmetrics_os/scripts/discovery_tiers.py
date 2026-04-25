"""Canonical discovery tier rules for throughput compare (all matrix presets).

Used by ``throughput_discovery_compare.py`` for A0–A5, B0–B4, and future variant
folders: same gates vs the experiment baseline role folder — no matrix-specific
hidden relax definitions.
"""

from __future__ import annotations

from typing import Any, Literal

PF_MIN_GATE = 1.25
RELAX_TRADE_MULT = 1.10  # strictly > 10% more trades than baseline
WATCHLIST_TRADE_MULT = 1.05  # >= 5% vs baseline
EXP_MATERIAL_SLACK = 0.08  # relax: expectancy not materially worse than baseline
DEFAULT_MAX_DD_WORSEN_RATIO = 1.2

CONFIDENCE_RANK: dict[str, int] = {
    "LOW": 0,
    "MEDIUM": 1,
    "HIGH": 2,
}

Tier = Literal["relax_candidate", "watchlist"] | None


def num(x: Any) -> float | None:
    if x is None:
        return None
    if isinstance(x, (int, float)):
        return float(x)
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def confidence_rank(value: Any) -> int | None:
    if value is None:
        return None
    key = str(value).strip().upper()
    if key in CONFIDENCE_RANK:
        return CONFIDENCE_RANK[key]
    return None


def confidence_not_worse_than_baseline(variant_conf: Any, baseline_conf: Any) -> bool:
    vb = confidence_rank(variant_conf)
    bb = confidence_rank(baseline_conf)
    if vb is None or bb is None:
        return False
    return vb >= bb


def dd_not_materially_worse(
    variant_dd: float | None,
    baseline_dd: float | None,
    *,
    max_worsen_ratio: float,
) -> bool:
    if variant_dd is None or baseline_dd is None or baseline_dd == 0:
        return False
    return (variant_dd / baseline_dd) <= max_worsen_ratio


def relax_candidate_ok(
    *,
    trades: float | None,
    baseline_trades: float,
    expectancy_r: float | None,
    baseline_expectancy_r: float | None,
    profit_factor: float | None,
    variant_max_dd_r: float | None,
    baseline_max_dd_r: float | None,
    variant_confidence: Any,
    baseline_confidence: Any,
    max_dd_worsen_ratio: float = DEFAULT_MAX_DD_WORSEN_RATIO,
) -> bool:
    """Strong discovery signal vs baseline (still not promotion)."""
    t = num(trades)
    if t is None or baseline_trades <= 0:
        return False
    if not (t > baseline_trades * RELAX_TRADE_MULT):
        return False
    e = num(expectancy_r)
    b_e = num(baseline_expectancy_r)
    if e is None or b_e is None:
        return False
    if e < b_e - EXP_MATERIAL_SLACK:
        return False
    pf = num(profit_factor)
    if pf is None or pf < PF_MIN_GATE:
        return False
    if not dd_not_materially_worse(
        variant_dd=variant_max_dd_r,
        baseline_dd=baseline_max_dd_r,
        max_worsen_ratio=max_dd_worsen_ratio,
    ):
        return False
    if not confidence_not_worse_than_baseline(variant_confidence, baseline_confidence):
        return False
    return True


def watchlist_ok(
    *,
    trades: float | None,
    baseline_trades: float,
    expectancy_r: float | None,
    profit_factor: float | None,
) -> bool:
    """Weak discovery signal vs baseline (explicitly non-promotional)."""
    t = num(trades)
    if t is None or baseline_trades <= 0:
        return False
    if not (t >= baseline_trades * WATCHLIST_TRADE_MULT):
        return False
    e = num(expectancy_r)
    if e is None or e <= 0:
        return False
    pf = num(profit_factor)
    if pf is None or pf < PF_MIN_GATE:
        return False
    return True


def classify_tier(
    *,
    trades: float | None,
    baseline_trades: float,
    expectancy_r: float | None,
    baseline_expectancy_r: float | None,
    profit_factor: float | None,
    variant_max_dd_r: float | None,
    baseline_max_dd_r: float | None,
    variant_confidence: Any,
    baseline_confidence: Any,
    max_dd_worsen_ratio: float = DEFAULT_MAX_DD_WORSEN_RATIO,
) -> Tier:
    if relax_candidate_ok(
        trades=trades,
        baseline_trades=baseline_trades,
        expectancy_r=expectancy_r,
        baseline_expectancy_r=baseline_expectancy_r,
        profit_factor=profit_factor,
        variant_max_dd_r=variant_max_dd_r,
        baseline_max_dd_r=baseline_max_dd_r,
        variant_confidence=variant_confidence,
        baseline_confidence=baseline_confidence,
        max_dd_worsen_ratio=max_dd_worsen_ratio,
    ):
        return "relax_candidate"
    if watchlist_ok(
        trades=trades,
        baseline_trades=baseline_trades,
        expectancy_r=expectancy_r,
        profit_factor=profit_factor,
    ):
        return "watchlist"
    return None


def discovery_rule_summary(*, max_dd_worsen_ratio: float) -> dict[str, Any]:
    """Structured summary for THROUGHPUT_COMPARE.json."""
    return {
        "version": "1.0",
        "scope": "All throughput discovery compare runs vs the selected baseline folder (A0–A5, B0–B4, future matrices).",
        "relax_candidate": {
            "trades": f"strictly greater than baseline × {RELAX_TRADE_MULT:.2f} (>{(RELAX_TRADE_MULT - 1) * 100:.0f}% trade count)",
            "expectancy_r": f"greater than or equal to baseline expectancy R minus {EXP_MATERIAL_SLACK} (material slack)",
            "profit_factor": f"greater than or equal to {PF_MIN_GATE}",
            "max_drawdown_r": (
                f"variant / baseline ratio must be less than or equal to {max_dd_worsen_ratio:.2f} "
                "(same order of magnitude as QuantOS promotion gate default)"
            ),
            "confidence": "ordinal must be greater than or equal to baseline (LOW < MEDIUM < HIGH); unknown fails",
        },
        "watchlist": {
            "trades": f"greater than or equal to baseline × {WATCHLIST_TRADE_MULT:.2f} (≥{(WATCHLIST_TRADE_MULT - 1) * 100:.0f}% trade count)",
            "expectancy_r": "strictly greater than 0",
            "profit_factor": f"greater than or equal to {PF_MIN_GATE}",
            "notes": "No DD or confidence requirement; not promotion; use only for next experiment design.",
        },
    }
