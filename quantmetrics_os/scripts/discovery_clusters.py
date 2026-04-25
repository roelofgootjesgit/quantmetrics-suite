"""Interpretive clustering for throughput compare (does not change tier classification).

Groups variants that land in the same discovery tier with near-identical headline
metrics so Markdown can summarize once. JSON still lists every variant row and
every tier line unchanged.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

# Lower = fewer deliberate config knobs vs baseline (heuristic for preferred_next_test).
# Unknown folders default to 99. Aligns with throughput matrix intent (single-filter relax first).
VARIANT_CONFIG_DELTA_RANK: dict[str, int] = {
    "a1_session_relaxed": 1,
    "a2_regime_relaxed": 1,
    "a3_cooldown_relaxed": 1,
    "a4_session_regime_relaxed": 2,
    "a5_throughput_discovery": 10,
    "b1_london_only_relaxed": 1,
    "b2_ny_only_relaxed": 1,
    "b3_overlap_relaxed": 1,
    "b4_full_session_relaxed": 1,
}


def _sig_num(x: Any, nd: int) -> float | None:
    if x is None:
        return None
    try:
        return round(float(x), nd)
    except (TypeError, ValueError):
        return None


def metric_cluster_key(
    *,
    total_trades: Any,
    expectancy_r: Any,
    profit_factor: Any,
    max_drawdown_r: Any,
) -> tuple[Any, ...]:
    """Near-equality bucket for trades / exp / PF / DD (canonical tier metrics)."""
    try:
        ti = int(float(total_trades)) if total_trades is not None else -1
    except (TypeError, ValueError):
        ti = -1
    return (
        ti,
        _sig_num(expectancy_r, 6),
        _sig_num(profit_factor, 6),
        _sig_num(max_drawdown_r, 6),
    )


def preferred_next_test(variants: list[str], *, variant_order: list[str]) -> str:
    def sort_key(vf: str) -> tuple[int, int, str]:
        rank = VARIANT_CONFIG_DELTA_RANK.get(vf, 99)
        try:
            oidx = variant_order.index(vf)
        except ValueError:
            oidx = 999
        return (rank, oidx, vf)

    return sorted(variants, key=sort_key)[0]


def build_discovery_clusters(
    tiered_rows: list[dict[str, Any]],
    *,
    variant_order: list[str],
) -> list[dict[str, Any]]:
    """Return cluster objects only for groups with >=2 variants in the same tier + metric bucket."""
    buckets: dict[tuple[str, tuple[Any, ...]], list[str]] = defaultdict(list)
    metrics_by_vf: dict[str, dict[str, Any]] = {}

    for row in tiered_rows:
        tier = row.get("tier")
        if tier not in ("relax_candidate", "watchlist"):
            continue
        vf = row.get("variant_folder")
        if not vf:
            continue
        key = metric_cluster_key(
            total_trades=row.get("total_trades"),
            expectancy_r=row.get("expectancy_r"),
            profit_factor=row.get("profit_factor"),
            max_drawdown_r=row.get("max_drawdown_r"),
        )
        buckets[(str(tier), key)].append(vf)
        metrics_by_vf[vf] = {
            "total_trades": row.get("total_trades"),
            "expectancy_r": row.get("expectancy_r"),
            "profit_factor": row.get("profit_factor"),
            "max_drawdown_r": row.get("max_drawdown_r"),
        }

    out: list[dict[str, Any]] = []
    for (tier, _sig), vfs in buckets.items():
        uniq = sorted(set(vfs))
        if len(uniq) < 2:
            continue
        pref = preferred_next_test(uniq, variant_order=variant_order)
        rep = metrics_by_vf.get(pref) or metrics_by_vf.get(uniq[0], {})
        out.append(
            {
                "tier": tier,
                "variants": uniq,
                "representative_metrics": rep,
                "preferred_next_test": pref,
                "rationale": (
                    f"`{pref}` is the preferred next single-variable test among this cluster "
                    "(lowest heuristic config-delta rank vs baseline; see VARIANT_CONFIG_DELTA_RANK in "
                    "quantmetrics_os/scripts/discovery_clusters.py)."
                ),
            }
        )
    out.sort(key=lambda c: (0 if c["tier"] == "relax_candidate" else 1, c["preferred_next_test"]))
    return out
