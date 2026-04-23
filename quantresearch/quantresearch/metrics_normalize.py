"""Normalize heterogeneous analytics / backtest dicts to comparable metric names."""

from __future__ import annotations

from typing import Any


def _num(x: Any) -> float | None:
    if x is None:
        return None
    if isinstance(x, (int, float)):
        return float(x)
    if isinstance(x, str):
        s = x.strip().rstrip("%")
        try:
            return float(s)
        except ValueError:
            return None
    return None


def _first(d: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for k in keys:
        if k in d and d[k] is not None:
            return d[k]
    return None


def normalize_metrics(raw: dict[str, Any] | None) -> dict[str, Any]:
    """Map aliases to canonical keys used by comparison_engine and logs."""
    if not raw:
        return {}

    out: dict[str, Any] = {}

    tc = _first(raw, ("trade_count", "total_trades", "trades", "n"))
    if tc is not None:
        try:
            out["trade_count"] = int(tc)
        except (TypeError, ValueError):
            pass

    mr = _num(_first(raw, ("mean_r", "expectancy_r")))
    if mr is not None:
        out["mean_r"] = mr

    tr = _num(_first(raw, ("total_r",)))
    if tr is not None:
        out["total_r"] = tr

    wr = _first(raw, ("win_rate_raw", "winrate"))
    if wr is None and "win_rate" in raw:
        wr = raw["win_rate"]
    wn = _num(wr)
    if wn is not None:
        if wn <= 1.0:
            out["winrate"] = wn * 100.0
        else:
            out["winrate"] = wn

    for key, aliases in (
        ("avg_win_r", ("avg_win_r",)),
        ("avg_loss_r", ("avg_loss_r",)),
        ("profit_factor", ("profit_factor",)),
        ("drawdown", ("drawdown", "max_drawdown_r")),
        ("avg_mae_r", ("avg_mae_r",)),
        ("avg_mfe_r", ("avg_mfe_r",)),
        ("mfe_capture_ratio", ("mfe_capture_ratio",)),
        ("signal_count", ("signal_count",)),
        ("enter_count", ("enter_count",)),
        ("no_action_count", ("no_action_count",)),
    ):
        v = _num(_first(raw, aliases))
        if v is not None:
            out[key] = v

    if "block_counts" in raw and isinstance(raw["block_counts"], dict):
        out["block_counts"] = dict(raw["block_counts"])

    # Pass-through slices if present (expectancy per regime/session/setup)
    for k in ("by_regime", "by_session", "by_setup_type", "context_slices"):
        if k in raw:
            out[k] = raw[k]

    return out
