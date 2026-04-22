"""Performance metrics from QuantLog events (Level B rerun comparison).

Uses realized ``trade_closed`` outcomes only — causal attribution from engine reruns.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from quantmetrics_analytics.datasets.closed_trades import trade_closed_events_to_df


def max_drawdown_r_from_pnls(pnls: list[float]) -> float:
    """Max drawdown in R from an ordered series of trade outcomes."""
    cum = 0.0
    peak = 0.0
    max_dd = 0.0
    for r in pnls:
        cum += float(r)
        peak = max(peak, cum)
        max_dd = min(max_dd, cum - peak)
    return float(max_dd)


def trade_performance_metrics(events: list[dict[str, Any]]) -> dict[str, Any]:
    """pnl_r-based stats for one run (filter events to a single ``run_id`` before calling)."""
    df = trade_closed_events_to_df(events)
    if df.empty:
        return {
            "trade_count": 0,
            "mean_r": 0.0,
            "sum_r": 0.0,
            "winrate_pct": 0.0,
            "wins": 0,
            "losses": 0,
            "max_dd_r": 0.0,
            "profit_factor_like": 0.0,
        }

    df = df.sort_values("timestamp_utc", na_position="first")
    rs = df["pnl_r"].astype(float)
    pnls = rs.tolist()
    n = len(df)
    wins = int((rs > 1e-12).sum())
    losses = int((rs < -1e-12).sum())
    wr = 100.0 * wins / n if n else 0.0
    sum_pos = float(rs[rs > 0].sum())
    sum_neg = float(abs(rs[rs < 0].sum()))
    pf = (sum_pos / sum_neg) if sum_neg > 1e-12 else (999.99 if sum_pos > 0 else 0.0)

    return {
        "trade_count": n,
        "mean_r": float(rs.mean()),
        "sum_r": float(rs.sum()),
        "winrate_pct": wr,
        "wins": wins,
        "losses": losses,
        "max_dd_r": max_drawdown_r_from_pnls(pnls),
        "profit_factor_like": pf,
    }


def guard_block_counts(events: list[dict[str, Any]], *, decisions: frozenset[str] | None = None) -> dict[str, int]:
    """Count ``risk_guard_decision`` rows per ``guard_name`` (default: BLOCK only)."""
    want = decisions or frozenset({"BLOCK"})
    c: Counter[str] = Counter()
    for ev in events:
        if ev.get("event_type") != "risk_guard_decision" or ev.get("source_system") != "quantbuild":
            continue
        pl = ev.get("payload") if isinstance(ev.get("payload"), dict) else {}
        if str(pl.get("decision") or "").strip().upper() not in want:
            continue
        g = pl.get("guard_name")
        if g is not None and str(g).strip():
            c[str(g).strip()] += 1
    return dict(sorted(c.items(), key=lambda x: (-x[1], x[0])))
