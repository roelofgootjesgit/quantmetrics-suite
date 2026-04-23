"""Backtest metrics: win rate, profit factor, expectancy, max drawdown, etc."""
from collections import defaultdict
from typing import Dict, List

from src.quantbuild.models.trade import Trade


def _compute_core_metrics(trades: List[Trade]) -> dict:
    if not trades:
        return {
            "total_trades": 0, "trade_count": 0, "wins": 0, "losses": 0,
            "win_rate": 0.0, "win_rate_01": 0.0, "profit_factor": 0.0,
            "expectancy": 0.0, "expectancy_r": 0.0, "total_profit_r": 0.0,
            "net_pnl": 0.0, "max_drawdown": 0.0, "avg_holding_hours": 0.0,
        }

    wins = [t for t in trades if t.result == "WIN"]
    losses = [t for t in trades if t.result == "LOSS"]
    total_r = sum(t.profit_r for t in trades)
    gross_profit_r = sum(t.profit_r for t in wins)
    gross_loss_r = abs(sum(t.profit_r for t in losses))
    pf = (gross_profit_r / gross_loss_r) if gross_loss_r else (gross_profit_r or 0.0)
    net_pnl = sum(t.profit_usd for t in trades)
    win_rate_pct = 100.0 * len(wins) / len(trades)
    expectancy_r = total_r / len(trades)

    equity = []
    cum = 0.0
    for t in trades:
        cum += t.profit_r
        equity.append(cum)
    peak = equity[0]
    max_dd = 0.0
    for v in equity:
        if v > peak:
            peak = v
        dd = peak - v
        if dd > max_dd:
            max_dd = dd

    holding_seconds = [(t.timestamp_close - t.timestamp_open).total_seconds() for t in trades]
    avg_holding_hours = (sum(holding_seconds) / len(holding_seconds) / 3600.0) if holding_seconds else 0.0

    return {
        "total_trades": len(trades), "trade_count": len(trades),
        "wins": len(wins), "losses": len(losses),
        "win_rate": win_rate_pct, "win_rate_01": len(wins) / len(trades),
        "profit_factor": pf, "expectancy": expectancy_r, "expectancy_r": expectancy_r,
        "total_profit_r": total_r, "net_pnl": net_pnl,
        "max_drawdown": -max_dd, "avg_holding_hours": avg_holding_hours,
    }


def compute_metrics(trades: List[Trade]) -> dict:
    return _compute_core_metrics(trades)


def compute_metrics_by_direction(trades: List[Trade]) -> Dict[str, dict]:
    by_dir: Dict[str, List[Trade]] = defaultdict(list)
    for t in trades:
        by_dir[t.direction].append(t)
    return {d: _compute_core_metrics(by_dir.get(d, [])) for d in ["LONG", "SHORT"]}


def compute_metrics_by_regime(trades: List[Trade]) -> Dict[str, dict]:
    by_regime: Dict[str, List[Trade]] = defaultdict(list)
    for t in trades:
        by_regime[t.regime or "UNKNOWN"].append(t)
    return {k: _compute_core_metrics(v) for k, v in sorted(by_regime.items())}


def compute_metrics_by_session(trades: List[Trade]) -> Dict[str, dict]:
    by_session: Dict[str, List[Trade]] = defaultdict(list)
    for t in trades:
        by_session[t.session or "UNKNOWN"].append(t)
    return {k: _compute_core_metrics(v) for k, v in sorted(by_session.items())}


def compute_full_report(trades: List[Trade]) -> dict:
    return {
        "overall": compute_metrics(trades),
        "by_direction": compute_metrics_by_direction(trades),
        "by_regime": compute_metrics_by_regime(trades),
        "by_session": compute_metrics_by_session(trades),
    }
