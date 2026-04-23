"""
Strategy Variants Backtest — SQE_STRICT vs SQE_MEDIUM vs SQE_LIGHT

Runs all three variants on 5-year Dukascopy data and produces
a full comparative analysis with institutional-grade metrics.
"""
import copy
import json
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.quantbuild.config import load_config
from src.quantbuild.backtest.engine import run_backtest
from src.quantbuild.models.trade import Trade

PERIOD_DAYS = 1825


def deep_merge(base: dict, override: dict) -> dict:
    result = copy.deepcopy(base)
    for k, v in override.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = deep_merge(result[k], v)
        else:
            result[k] = v
    return result


# ── Strategy variant configs ─────────────────────────────────────────────

def _backtest_risk_overrides(cfg: dict, max_tps: int = 1) -> dict:
    """For backtesting: disable equity kill switch, set session limit."""
    cfg.setdefault("risk", {})
    cfg["risk"]["equity_kill_switch_pct"] = 999.0
    cfg["risk"]["max_daily_loss_r"] = 999.0
    cfg["risk"]["max_trades_per_session"] = max_tps
    return cfg


def make_baseline(base_cfg: dict) -> dict:
    """BASELINE: No regime detection, 3 trades/session (previous best)."""
    cfg = copy.deepcopy(base_cfg)
    cfg["backtest"]["default_period_days"] = PERIOD_DAYS
    cfg.pop("regime", None)
    cfg.pop("regime_profiles", None)
    return _backtest_risk_overrides(cfg, max_tps=3)


def make_prod_v1(base_cfg: dict) -> dict:
    """PROD_V1: SKIP_COMP, same 2:1 everywhere, no session filter per regime."""
    cfg = load_config("configs/strict_prod_v1.yaml")
    cfg["backtest"]["default_period_days"] = PERIOD_DAYS
    return _backtest_risk_overrides(cfg, max_tps=3)


def make_prod_v2(base_cfg: dict) -> dict:
    """PROD_V2: SKIP_COMP + expansion only NY/Overlap after 10:00 UTC."""
    cfg = load_config("configs/strict_prod_v2.yaml")
    cfg["backtest"]["default_period_days"] = PERIOD_DAYS
    return _backtest_risk_overrides(cfg, max_tps=3)


# ── Detailed metrics ─────────────────────────────────────────────────────

def compute_detailed_metrics(trades: List[Trade]) -> dict:
    if not trades:
        return {"error": "no trades"}

    wins = [t for t in trades if t.result == "WIN"]
    losses = [t for t in trades if t.result == "LOSS"]
    timeouts = [t for t in trades if t.result == "TIMEOUT"]

    win_rs = [t.profit_r for t in wins]
    loss_rs = [t.profit_r for t in losses]
    all_rs = [t.profit_r for t in trades]

    avg_win_r = sum(win_rs) / len(win_rs) if win_rs else 0.0
    avg_loss_r = sum(loss_rs) / len(loss_rs) if loss_rs else 0.0
    total_r = sum(all_rs)
    expectancy_r = total_r / len(trades)
    win_rate = len(wins) / len(trades)

    gross_profit = sum(r for r in all_rs if r > 0)
    gross_loss = abs(sum(r for r in all_rs if r < 0))
    pf = gross_profit / gross_loss if gross_loss > 0 else float("inf")

    # Equity curve + max drawdown
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

    # Longest losing streak
    current_streak = 0
    max_losing_streak = 0
    current_win_streak = 0
    max_win_streak = 0
    for t in trades:
        if t.result == "LOSS" or t.result == "TIMEOUT":
            current_streak += 1
            current_win_streak = 0
        else:
            current_win_streak += 1
            max_losing_streak = max(max_losing_streak, current_streak)
            current_streak = 0
        max_win_streak = max(max_win_streak, current_win_streak)
    max_losing_streak = max(max_losing_streak, current_streak)

    # Holding time
    holding_hours = [(t.timestamp_close - t.timestamp_open).total_seconds() / 3600 for t in trades]
    avg_holding = sum(holding_hours) / len(holding_hours) if holding_hours else 0

    # Per-year breakdown
    by_year: Dict[int, List[Trade]] = defaultdict(list)
    for t in trades:
        by_year[t.timestamp_open.year].append(t)
    yearly = {}
    for year in sorted(by_year.keys()):
        yt = by_year[year]
        yr = sum(t.profit_r for t in yt)
        yw = sum(1 for t in yt if t.result == "WIN")
        yearly[year] = {
            "trades": len(yt),
            "wins": yw,
            "win_rate": f"{100 * yw / len(yt):.1f}%",
            "net_r": round(yr, 2),
        }

    # Per-direction
    long_trades = [t for t in trades if t.direction == "LONG"]
    short_trades = [t for t in trades if t.direction == "SHORT"]
    long_r = sum(t.profit_r for t in long_trades)
    short_r = sum(t.profit_r for t in short_trades)

    # Best/worst trade
    best = max(trades, key=lambda t: t.profit_r)
    worst = min(trades, key=lambda t: t.profit_r)

    # Median win/loss
    sorted_wins = sorted(win_rs, reverse=True)
    sorted_losses = sorted(loss_rs)
    median_win = sorted_wins[len(sorted_wins) // 2] if sorted_wins else 0
    median_loss = sorted_losses[len(sorted_losses) // 2] if sorted_losses else 0

    period_years = PERIOD_DAYS / 365.25
    trades_per_year = len(trades) / period_years
    trades_per_month = trades_per_year / 12
    r_per_year = total_r / period_years

    # At 1% risk
    annual_return_pct = r_per_year * 1.0  # 1% per R
    monthly_return_pct = annual_return_pct / 12

    return {
        "total_trades": len(trades),
        "wins": len(wins),
        "losses": len(losses),
        "timeouts": len(timeouts),
        "win_rate": f"{100 * win_rate:.1f}%",
        "win_rate_raw": win_rate,
        "profit_factor": round(pf, 2),
        "expectancy_r": round(expectancy_r, 3),
        "total_r": round(total_r, 2),
        "max_drawdown_r": round(-max_dd, 2),
        "avg_win_r": round(avg_win_r, 3),
        "avg_loss_r": round(avg_loss_r, 3),
        "median_win_r": round(median_win, 3),
        "median_loss_r": round(median_loss, 3),
        "best_trade_r": round(best.profit_r, 3),
        "worst_trade_r": round(worst.profit_r, 3),
        "longest_losing_streak": max_losing_streak,
        "longest_winning_streak": max_win_streak,
        "avg_holding_hours": round(avg_holding, 1),
        "trades_per_year": round(trades_per_year, 1),
        "trades_per_month": round(trades_per_month, 1),
        "r_per_year": round(r_per_year, 2),
        "annual_return_1pct_risk": f"{annual_return_pct:.1f}%",
        "monthly_return_1pct_risk": f"{monthly_return_pct:.2f}%",
        "long_trades": len(long_trades),
        "short_trades": len(short_trades),
        "long_r": round(long_r, 2),
        "short_r": round(short_r, 2),
        "by_year": yearly,
    }


def print_metrics(name: str, m: dict) -> None:
    print(f"\n{'='*60}")
    print(f"  {name}")
    print(f"{'='*60}")

    print(f"\n  CORE METRICS")
    print(f"  {'Trades':<28} {m['total_trades']}")
    print(f"  {'Wins / Losses / Timeouts':<28} {m['wins']} / {m['losses']} / {m['timeouts']}")
    print(f"  {'Win Rate':<28} {m['win_rate']}")
    print(f"  {'Profit Factor':<28} {m['profit_factor']}")
    print(f"  {'Expectancy':<28} {m['expectancy_r']}R per trade")
    print(f"  {'Total R':<28} {m['total_r']}R")
    print(f"  {'Max Drawdown':<28} {m['max_drawdown_r']}R")

    print(f"\n  WIN/LOSS DETAIL")
    print(f"  {'Avg Win':<28} {m['avg_win_r']}R")
    print(f"  {'Avg Loss':<28} {m['avg_loss_r']}R")
    print(f"  {'Median Win':<28} {m['median_win_r']}R")
    print(f"  {'Median Loss':<28} {m['median_loss_r']}R")
    print(f"  {'Best Trade':<28} {m['best_trade_r']}R")
    print(f"  {'Worst Trade':<28} {m['worst_trade_r']}R")

    print(f"\n  STREAKS")
    print(f"  {'Longest Losing Streak':<28} {m['longest_losing_streak']}")
    print(f"  {'Longest Winning Streak':<28} {m['longest_winning_streak']}")

    print(f"\n  FREQUENCY")
    print(f"  {'Trades / Year':<28} {m['trades_per_year']}")
    print(f"  {'Trades / Month':<28} {m['trades_per_month']}")
    print(f"  {'Avg Holding Time':<28} {m['avg_holding_hours']}h")

    print(f"\n  RETURNS (1% risk per trade)")
    print(f"  {'R per Year':<28} {m['r_per_year']}R")
    print(f"  {'Annual Return':<28} {m['annual_return_1pct_risk']}")
    print(f"  {'Monthly Return':<28} {m['monthly_return_1pct_risk']}")

    print(f"\n  DIRECTION SPLIT")
    print(f"  {'LONG':<28} {m['long_trades']} trades  ->  {m['long_r']}R")
    print(f"  {'SHORT':<28} {m['short_trades']} trades  ->  {m['short_r']}R")

    print(f"\n  YEARLY BREAKDOWN")
    for year, yd in m["by_year"].items():
        print(f"  {year}:  {yd['trades']:>3} trades  WR {yd['win_rate']:>6}  net {yd['net_r']:>+7.2f}R")


def print_comparison(results: Dict[str, dict]) -> None:
    print(f"\n\n{'='*70}")
    print(f"  STRATEGY COMPARISON — 5 YEAR XAUUSD (15m)")
    print(f"{'='*70}")

    header = f"  {'Metric':<28}"
    for name in results:
        header += f" {name:>12}"
    print(header)
    print(f"  {'-'*64}")

    metrics_to_show = [
        ("Trades", "total_trades"),
        ("Win Rate", "win_rate"),
        ("Profit Factor", "profit_factor"),
        ("Expectancy", "expectancy_r", "R"),
        ("Total R", "total_r", "R"),
        ("Max Drawdown", "max_drawdown_r", "R"),
        ("Avg Win", "avg_win_r", "R"),
        ("Avg Loss", "avg_loss_r", "R"),
        ("Longest Lose Streak", "longest_losing_streak"),
        ("Trades/Year", "trades_per_year"),
        ("Trades/Month", "trades_per_month"),
        ("R/Year", "r_per_year", "R"),
        ("Annual Return @1%", "annual_return_1pct_risk"),
        ("Monthly Return @1%", "monthly_return_1pct_risk"),
    ]

    for item in metrics_to_show:
        label = item[0]
        key = item[1]
        suffix = item[2] if len(item) > 2 else ""
        row = f"  {label:<28}"
        for name, m in results.items():
            val = m.get(key, "—")
            if isinstance(val, float):
                val = f"{val:.2f}{suffix}"
            else:
                val = f"{val}{suffix}" if suffix and not str(val).endswith(suffix) and not str(val).endswith("%") else str(val)
            row += f" {val:>12}"
        print(row)

    # Ensemble projection
    print(f"\n  {'-'*64}")
    print(f"  ENSEMBLE PROJECTION (all three combined)")
    total_trades = sum(m["total_trades"] for m in results.values())
    total_r = sum(m["total_r"] for m in results.values())
    period_years = PERIOD_DAYS / 365.25
    ensemble_tpy = total_trades / period_years
    ensemble_rpy = total_r / period_years
    ensemble_exp = total_r / total_trades if total_trades > 0 else 0

    print(f"  {'Total Trades':<28} {total_trades}")
    print(f"  {'Trades/Year':<28} {ensemble_tpy:.0f}")
    print(f"  {'Trades/Month':<28} {ensemble_tpy/12:.1f}")
    print(f"  {'Avg Expectancy':<28} {ensemble_exp:.3f}R")
    print(f"  {'R/Year':<28} {ensemble_rpy:.1f}R")
    print(f"  {'Annual Return @1%':<28} {ensemble_rpy:.1f}%")
    print(f"  {'Monthly Return @1%':<28} {ensemble_rpy/12:.2f}%")

    # FTMO assessment
    print(f"\n  {'-'*64}")
    print(f"  FTMO ASSESSMENT (10% target in 30 days @ 1% risk)")
    ftmo_r_needed = 10.0
    ensemble_tpm = ensemble_tpy / 12
    ensemble_r_per_month = ensemble_rpy / 12
    if ensemble_r_per_month > 0:
        months_to_target = ftmo_r_needed / ensemble_r_per_month
        print(f"  {'R needed':<28} {ftmo_r_needed}R")
        print(f"  {'R/Month (ensemble)':<28} {ensemble_r_per_month:.2f}R")
        print(f"  {'Months to 10R':<28} {months_to_target:.1f}")
        print(f"  {'Trades/Month (ensemble)':<28} {ensemble_tpm:.1f}")
        feasible = "YES" if months_to_target <= 1.5 else "BORDERLINE" if months_to_target <= 3 else "NO (need more frequency)"
        print(f"  {'FTMO feasible?':<28} {feasible}")
    else:
        print(f"  Not feasible — negative expectancy")


def main():
    print("Loading config...")
    base_cfg = load_config(str(Path(__file__).resolve().parents[1] / "configs" / "xauusd.yaml"))

    variants = {
        "BASELINE": make_baseline(base_cfg),
        "PROD_V1": make_prod_v1(base_cfg),
        "PROD_V2": make_prod_v2(base_cfg),
    }

    results = {}
    all_trades = {}

    for name, cfg in variants.items():
        print(f"\n{'-'*60}")
        print(f"  Running {name}...")
        print(f"{'-'*60}")
        trades = run_backtest(cfg)
        all_trades[name] = trades
        m = compute_detailed_metrics(trades)
        results[name] = m
        print_metrics(name, m)

    print_comparison(results)

    # Save results
    out_dir = Path(__file__).resolve().parents[1] / "reports" / "latest"
    out_dir.mkdir(parents=True, exist_ok=True)

    serializable = {}
    for name, m in results.items():
        sm = {k: v for k, v in m.items() if k != "by_year"}
        sm["by_year"] = {str(k): v for k, v in m.get("by_year", {}).items()}
        serializable[name] = sm

    with open(out_dir / "strategy_variants.json", "w") as f:
        json.dump(serializable, f, indent=2, default=str)
    print(f"\nResults saved to {out_dir / 'strategy_variants.json'}")


if __name__ == "__main__":
    main()
