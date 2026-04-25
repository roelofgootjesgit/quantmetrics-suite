from __future__ import annotations

from collections import defaultdict
from datetime import datetime

from .models import DecisionCycle


def _sample_quality(n: int) -> str:
    if n < 20:
        return "INSUFFICIENT_DATA"
    if n < 50:
        return "WEAK_EVIDENCE"
    if n < 100:
        return "USABLE"
    return "STRONGER_EVIDENCE"


def _profit_factor(pnls: list[float]) -> float | None:
    wins = sum(v for v in pnls if v > 0)
    losses = abs(sum(v for v in pnls if v < 0))
    if losses == 0:
        return None if wins == 0 else float("inf")
    return wins / losses


def _max_drawdown_r(pnls: list[float]) -> float:
    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    for pnl in pnls:
        equity += pnl
        peak = max(peak, equity)
        max_dd = min(max_dd, equity - peak)
    return abs(max_dd)


def _verdict(expectancy: float | None, pf: float | None, n: int) -> str:
    if expectancy is None:
        return "UNSTABLE"
    if expectancy > 0 and pf is not None and pf > 1.2 and n >= 50:
        return "PROMISING"
    if expectancy > 0 and n < 50:
        return "PROMISING_BUT_WEAK"
    if expectancy < 0:
        return "WEAK_OR_NEGATIVE"
    return "UNSTABLE"


def _month_and_quarter(timestamp_utc: str | None) -> tuple[str | None, str | None]:
    if not timestamp_utc:
        return None, None
    cleaned = timestamp_utc.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(cleaned)
    except ValueError:
        return None, None
    quarter = (dt.month - 1) // 3 + 1
    return f"{dt.year:04d}-{dt.month:02d}", f"{dt.year:04d}-Q{quarter}"


def analyze_stability(cycles: list[DecisionCycle]) -> dict:
    breakdown_keys = ["symbol", "regime", "session", "month", "quarter", "guard_name"]
    grouped: dict[str, dict[str, list[DecisionCycle]]] = {name: defaultdict(list) for name in breakdown_keys}

    for cycle in cycles:
        month, quarter = _month_and_quarter(cycle.timestamp_utc)
        grouped["symbol"][cycle.symbol or "UNKNOWN"].append(cycle)
        grouped["regime"][cycle.regime or "UNKNOWN"].append(cycle)
        grouped["session"][cycle.session or "UNKNOWN"].append(cycle)
        grouped["month"][month or "UNKNOWN"].append(cycle)
        grouped["quarter"][quarter or "UNKNOWN"].append(cycle)
        grouped["guard_name"][cycle.guard_name or "UNKNOWN_GUARD"].append(cycle)

    output: dict[str, list[dict]] = {}
    for dimension, buckets in grouped.items():
        rows = []
        for label, bucket_cycles in sorted(buckets.items()):
            pnls = [c.pnl_r for c in bucket_cycles if c.trade_closed and c.pnl_r is not None]
            pnl_values = [float(v) for v in pnls]
            n = len(pnl_values)
            expectancy = (sum(pnl_values) / n) if n else None
            pf = _profit_factor(pnl_values)
            mfe_values = [c.mfe_r for c in bucket_cycles if c.mfe_r is not None]
            mae_values = [c.mae_r for c in bucket_cycles if c.mae_r is not None]

            rows.append(
                {
                    dimension: label,
                    "trade_count": n,
                    "expectancy_r": expectancy,
                    "win_rate": (sum(1 for x in pnl_values if x > 0) / n) if n else None,
                    "profit_factor": pf,
                    "max_drawdown_r": _max_drawdown_r(pnl_values) if pnl_values else None,
                    "avg_mfe_r": (sum(mfe_values) / len(mfe_values)) if mfe_values else None,
                    "avg_mae_r": (sum(mae_values) / len(mae_values)) if mae_values else None,
                    "sample_quality": _sample_quality(n),
                    "verdict": _verdict(expectancy, pf, n),
                }
            )
        output[dimension] = rows

    return output

