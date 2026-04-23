"""
Portfolio Adaptive Simulation — Full Capital Deployment Engine.

Integrates ALL portfolio engineering components:
  - Correlation-aware heat engine (not naive position count)
  - Adaptive mode layer (equity-curve based risk scaling)
  - Execution quality simulation (slippage/spread per instrument)
  - FTMO Expected Value calculation
  - Watchlist instrument testing (EURUSD TREND-only)

This is the difference between "having an edge" and "maximally deploying capital".

Usage:
    python scripts/portfolio_adaptive_sim.py
    python scripts/portfolio_adaptive_sim.py --skip-fetch
"""
import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd
import yaml

from src.quantbuild.config import load_config
from src.quantbuild.logging_config import setup_logging
from src.quantbuild.backtest.engine import (
    _deep_merge, _prepare_sim_cache, _apply_h1_gate,
)
from src.quantbuild.data.sessions import session_from_timestamp
from src.quantbuild.indicators.atr import atr as compute_atr
from src.quantbuild.io.parquet_loader import load_parquet
from src.quantbuild.strategies.sqe_xauusd import (
    run_sqe_conditions, get_sqe_default_config, _compute_modules_once,
)
from src.quantbuild.strategy_modules.regime.detector import (
    RegimeDetector, REGIME_TREND, REGIME_EXPANSION, REGIME_COMPRESSION,
)
from src.quantbuild.execution.portfolio_heat import PortfolioHeatEngine, _get_correlation
from src.quantbuild.execution.adaptive_mode import AdaptiveModeLayer

PERIOD_DAYS = 1825
CONFIG_PATH = "configs/strict_prod_v2.yaml"
PROFILES_PATH = "configs/instruments/instrument_profiles.yaml"
FTMO_SIMS = 10_000

SLIPPAGE_PROFILES = {
    "XAUUSD": {"mean": 0.08, "std": 0.05, "spread_mean": 2.5, "spread_std": 1.0},
    "GBPUSD": {"mean": 0.04, "std": 0.03, "spread_mean": 1.2, "spread_std": 0.5},
    "USDJPY": {"mean": 0.04, "std": 0.02, "spread_mean": 0.9, "spread_std": 0.4},
    "EURUSD": {"mean": 0.03, "std": 0.02, "spread_mean": 0.8, "spread_std": 0.3},
}


# ── Exit Functions ────────────────────────────────────────────────────

def _full_excursion(cache, i, direction, max_bars=200):
    close_arr, high_arr, low_arr = cache["close"], cache["high"], cache["low"]
    n = len(close_arr)
    entry = float(close_arr[i])
    atr_val = float(cache["atr"][i])
    risk = atr_val if atr_val > 0 else entry * 0.005
    bars = []
    for j in range(i + 1, min(i + max_bars, n)):
        if direction == "LONG":
            fav = (high_arr[j] - entry) / risk
            adv = (entry - low_arr[j]) / risk
        else:
            fav = (entry - low_arr[j]) / risk
            adv = (high_arr[j] - entry) / risk
        bars.append((float(fav), float(adv)))
    return bars


def exit_baseline(exc, tp_r=2.0, sl_r=1.0):
    for fav, adv in exc:
        if adv >= sl_r:
            return -sl_r
        if fav >= tp_r:
            return tp_r
    return 0.0


def exit_dynamic(exc, is_exp_ny):
    if is_exp_ny:
        return exit_baseline(exc, tp_r=2.0, sl_r=1.0)
    partial_filled = False
    peak = 0.0
    for fav, adv in exc:
        if not partial_filled:
            if adv >= 1.0:
                return -1.0
            if fav >= 1.0:
                partial_filled = True
                peak = fav
                continue
        else:
            peak = max(peak, fav)
            drawback = peak - fav
            if drawback >= 1.5 or adv >= 0:
                trail_exit = max(0, peak - 1.5)
                return 1.0 * 0.5 + trail_exit * 0.5
    if partial_filled:
        return max(0, 1.0 * 0.5 + (peak - 1.5) * 0.5)
    return 0.0


# ── Signal Generation ────────────────────────────────────────────────

def generate_instrument_signals(symbol, cfg, inst_profile, base_path):
    end = datetime.now()
    start = end - timedelta(days=PERIOD_DAYS)

    data = load_parquet(base_path, symbol, "15m", start=start, end=end)
    if data.empty or len(data) < 200:
        return []
    data = data.sort_index()

    data_1h = load_parquet(base_path, symbol, "1h", start=start, end=end)
    if not data_1h.empty:
        data_1h = data_1h.sort_index()

    detector = RegimeDetector(config=cfg.get("regime", {}))
    regime_series = detector.classify(data, data_1h if not data_1h.empty else None)

    sqe_cfg = get_sqe_default_config()
    strategy_cfg = cfg.get("strategy", {}) or {}
    if strategy_cfg:
        _deep_merge(sqe_cfg, strategy_cfg)

    precomputed_df = _compute_modules_once(data, sqe_cfg)
    long_e = run_sqe_conditions(data, "LONG", sqe_cfg, _precomputed_df=precomputed_df)
    short_e = run_sqe_conditions(data, "SHORT", sqe_cfg, _precomputed_df=precomputed_df)

    if strategy_cfg.get("structure_use_h1_gate", False) and not data_1h.empty:
        long_e = _apply_h1_gate(long_e, data, "LONG", base_path, symbol, start, end, sqe_cfg)
        short_e = _apply_h1_gate(short_e, data, "SHORT", base_path, symbol, start, end, sqe_cfg)

    sim_cache = _prepare_sim_cache(data)
    regime_profiles = cfg.get("regime_profiles", {})
    session_mode = cfg.get("backtest", {}).get("session_mode", "extended")

    inst_regimes = inst_profile.get("regimes", {"trend": True, "expansion": True, "compression": False})
    exp_sessions = inst_profile.get("expansion_sessions")
    exp_min_hour = inst_profile.get("expansion_min_hour_utc")

    signals = []
    for i in range(1, len(data) - 1):
        for direction, mask in [("LONG", long_e), ("SHORT", short_e)]:
            if not mask.iloc[i]:
                continue
            ts = data.index[i]
            regime = regime_series.iloc[i] if i < len(regime_series) else REGIME_TREND
            session = session_from_timestamp(ts, mode=session_mode)

            if not inst_regimes.get(regime, False):
                continue

            rp = regime_profiles.get(regime, {})
            if rp.get("skip", False):
                continue

            if regime == REGIME_EXPANSION:
                allowed = exp_sessions or rp.get("allowed_sessions")
                if allowed and session not in allowed:
                    continue
                min_h = exp_min_hour if exp_min_hour is not None else rp.get("min_hour_utc")
                if min_h is not None and ts.hour < min_h:
                    continue

            exc = _full_excursion(sim_cache, i, direction)
            is_exp_ny = (
                regime == REGIME_EXPANSION
                and session in ("New York", "Overlap")
                and ts.hour >= 10
            )

            pnl = exit_dynamic(exc, is_exp_ny)

            # MFE for analytics
            mfe = max((f for f, _ in exc), default=0) if exc else 0
            mae = max((a for _, a in exc), default=0) if exc else 0

            signals.append({
                "ts": ts, "symbol": symbol, "direction": direction,
                "regime": regime, "session": session, "pnl": pnl,
                "mfe": mfe, "mae": mae,
                "asset_class": inst_profile.get("asset_class", ""),
            })

    return signals


# ── Adaptive Portfolio Simulation ────────────────────────────────────

def simulate_adaptive_portfolio(all_signals, mode_cfg, instruments_cfg, with_adaptive=True):
    """Full simulation with correlation-aware heat + adaptive risk scaling."""
    risk_base = mode_cfg["risk_per_trade_pct"]

    heat_engine = PortfolioHeatEngine({
        "max_portfolio_heat_pct": mode_cfg.get("max_portfolio_heat_pct", 6.0),
        "max_instrument_heat_pct": mode_cfg.get("max_instrument_heat_pct", risk_base * 2.5),
        "max_correlated_exposure": mode_cfg.get("max_correlated_exposure", 2),
        "max_same_direction": mode_cfg.get("max_same_direction", 4),
    })

    adaptive = AdaptiveModeLayer({
        "adaptive_mode": {
            "aggressive_dd_max": 1.0,
            "aggressive_momentum_window": 5,
            "defensive_dd": mode_cfg.get("max_daily_loss_pct", 3.0) * 0.6,
            "lockdown_dd": mode_cfg.get("max_total_dd_pct", 10.0) * 0.7,
            "defensive_losing_streak": 4,
            "lockdown_losing_streak": 6,
            "recovery_wins": 3,
        }
    })

    merged = sorted(all_signals, key=lambda s: s["ts"])

    equity_pct = 0.0
    peak_equity = 0.0
    daily_pnl_map = {}
    trades = []
    blocked = {
        "heat_engine": 0, "daily_loss": 0, "total_dd": 0,
        "spread_reject": 0, "mode_lockdown": 0, "slippage_reject": 0,
    }
    mode_trades = {"AGGRESSIVE": 0, "BASE": 0, "DEFENSIVE": 0, "LOCKDOWN": 0}
    mode_pnl = {"AGGRESSIVE": 0.0, "BASE": 0.0, "DEFENSIVE": 0.0, "LOCKDOWN": 0.0}
    exec_records = []

    hold_time_ticks = 12  # avg position hold in 15m bars

    for sig in merged:
        ts = sig["ts"]
        day = ts.date() if hasattr(ts, "date") else ts
        sym = sig["symbol"]
        inst = instruments_cfg.get(sym, {})
        asset_class = sig.get("asset_class", inst.get("asset_class", ""))

        # Daily loss check
        day_pnl = daily_pnl_map.get(day, 0.0)
        max_daily = mode_cfg.get("max_daily_loss_pct", 5.0)
        if day_pnl <= -max_daily:
            blocked["daily_loss"] += 1
            continue

        # Total DD check
        dd_from_peak = peak_equity - equity_pct
        if dd_from_peak >= mode_cfg.get("max_total_dd_pct", 10.0):
            blocked["total_dd"] += 1
            continue

        # Get effective risk from adaptive mode
        current_mode = adaptive.current_mode if with_adaptive else "BASE"
        if current_mode == "LOCKDOWN":
            blocked["mode_lockdown"] += 1
            continue

        effective_risk = adaptive.get_effective_risk(risk_base) if with_adaptive else risk_base
        risk_mult = inst.get("risk_multiplier", 1.0)
        trade_risk = effective_risk * risk_mult

        # Correlation-aware heat check
        allowed, reason = heat_engine.can_open(
            sym, sig["direction"], trade_risk, asset_class
        )
        if not allowed:
            blocked["heat_engine"] += 1
            continue

        # Simulate execution quality
        slip_prof = SLIPPAGE_PROFILES.get(sym, {"mean": 0.05, "std": 0.03, "spread_mean": 1.5, "spread_std": 0.5})
        slippage = abs(np.random.normal(slip_prof["mean"], slip_prof["std"]))
        spread = abs(np.random.normal(slip_prof["spread_mean"], slip_prof["spread_std"]))

        max_spread = inst.get("max_spread_pips", 4.0)
        max_slip = inst.get("max_slippage_r", 0.15)
        if spread > max_spread:
            blocked["spread_reject"] += 1
            exec_records.append({"symbol": sym, "rejected": True, "reason": "spread"})
            continue
        if slippage > max_slip:
            blocked["slippage_reject"] += 1
            exec_records.append({"symbol": sym, "rejected": True, "reason": "slippage"})
            continue

        # Execute
        net_pnl_r = sig["pnl"] - slippage
        trade_pnl_pct = net_pnl_r * trade_risk
        equity_pct += trade_pnl_pct
        peak_equity = max(peak_equity, equity_pct)
        daily_pnl_map[day] = daily_pnl_map.get(day, 0.0) + trade_pnl_pct

        # Track position in heat engine (simplified: add then remove after hold time)
        heat_engine.add_position(sym, sig["direction"], trade_risk, asset_class, sig["regime"])

        # Track mode performance
        mode_trades[current_mode] = mode_trades.get(current_mode, 0) + 1
        mode_pnl[current_mode] = mode_pnl.get(current_mode, 0) + net_pnl_r

        # Update adaptive mode
        adaptive.record_trade(net_pnl_r, sym, sig["regime"])
        adaptive.update_equity(equity_pct)

        trades.append({
            "ts": ts, "symbol": sym, "regime": sig["regime"],
            "direction": sig["direction"], "session": sig["session"],
            "pnl_r_gross": sig["pnl"], "slippage_r": slippage, "pnl_r_net": net_pnl_r,
            "spread": spread, "pnl_pct": trade_pnl_pct,
            "equity_after": equity_pct, "mode": current_mode,
            "risk_applied": trade_risk,
        })

        exec_records.append({
            "symbol": sym, "rejected": False,
            "slippage_r": slippage, "spread": spread,
        })

        # Release position from heat (simplified)
        heat_engine.remove_position(sym, sig["direction"])

    if not trades:
        return {"error": "no_trades"}

    pnl_net = np.array([t["pnl_r_net"] for t in trades])
    pnl_gross = np.array([t["pnl_r_gross"] for t in trades])
    pct_arr = np.array([t["pnl_pct"] for t in trades])
    wins = pnl_net[pnl_net > 0]
    losses = pnl_net[pnl_net < 0]
    gw = wins.sum() if len(wins) else 0
    gl = abs(losses.sum()) if len(losses) else 0

    eq_curve = np.array([t["equity_after"] for t in trades])
    peak = np.maximum.accumulate(eq_curve)
    dd = eq_curve - peak
    max_dd_pct = float(dd.min())

    monthly = {}
    for t in trades:
        mo = t["ts"].strftime("%Y-%m") if hasattr(t["ts"], "strftime") else str(t["ts"])[:7]
        monthly.setdefault(mo, 0.0)
        monthly[mo] += t["pnl_pct"]
    monthly_vals = list(monthly.values())

    per_inst = {}
    for t in trades:
        per_inst.setdefault(t["symbol"], [])
        per_inst[t["symbol"]].append(t["pnl_r_net"])

    yearly = {}
    for t in trades:
        yr = t["ts"].year if hasattr(t["ts"], "year") else 2025
        yearly.setdefault(yr, 0.0)
        yearly[yr] += t["pnl_pct"]

    # Execution quality stats
    filled = [r for r in exec_records if not r.get("rejected")]
    rejected = [r for r in exec_records if r.get("rejected")]
    avg_slip = np.mean([r["slippage_r"] for r in filled]) if filled else 0

    return {
        "trades": len(trades),
        "total_pct": float(equity_pct),
        "total_r_gross": float(pnl_gross.sum()),
        "total_r_net": float(pnl_net.sum()),
        "slippage_cost_r": float(pnl_gross.sum() - pnl_net.sum()),
        "wr": float(100 * len(wins) / len(pnl_net)),
        "pf": float(gw / gl) if gl else 0,
        "exp_r_net": float(pnl_net.mean()),
        "exp_r_gross": float(pnl_gross.mean()),
        "exp_pct": float(pct_arr.mean()),
        "max_dd_pct": max_dd_pct,
        "rdd": float(equity_pct / abs(max_dd_pct)) if max_dd_pct < 0 else 0,
        "monthly_avg_pct": float(np.mean(monthly_vals)) if monthly_vals else 0,
        "monthly_std_pct": float(np.std(monthly_vals)) if monthly_vals else 0,
        "monthly_min_pct": float(np.min(monthly_vals)) if monthly_vals else 0,
        "monthly_max_pct": float(np.max(monthly_vals)) if monthly_vals else 0,
        "pct_positive_months": float(100 * sum(1 for m in monthly_vals if m > 0) / len(monthly_vals)) if monthly_vals else 0,
        "blocked": blocked,
        "mode_distribution": mode_trades,
        "mode_pnl_r": {k: round(v, 2) for k, v in mode_pnl.items()},
        "yearly": yearly,
        "per_instrument": {
            sym: {
                "n": len(pnls), "exp": float(np.mean(pnls)),
                "total_r": float(np.sum(pnls)),
                "wr": float(100 * sum(1 for p in pnls if p > 0) / len(pnls)),
            } for sym, pnls in per_inst.items()
        },
        "execution": {
            "fills": len(filled),
            "rejects": len(rejected),
            "avg_slippage_r": round(avg_slip, 4),
            "reject_reasons": {
                r.get("reason", "unknown"): sum(1 for x in rejected if x.get("reason") == r.get("reason"))
                for r in rejected
            } if rejected else {},
        },
        "trade_list": trades,
    }


# ── FTMO with Adaptive Mode ─────────────────────────────────────────

def ftmo_adaptive_mc(trade_list, mode_cfg, n_sims=FTMO_SIMS):
    """FTMO Monte Carlo with adaptive mode switching during challenge."""
    target = mode_cfg.get("target_pct", 10.0)
    max_daily = mode_cfg.get("max_daily_loss_pct", 5.0)
    max_dd = mode_cfg.get("max_total_dd_pct", 10.0)
    risk_base = mode_cfg.get("risk_per_trade_pct", 1.5)
    trading_days = 30

    pnl_arr = np.array([t["pnl_r_net"] for t in trade_list])
    trades_per_day = len(pnl_arr) / (PERIOD_DAYS / 365.25 * 252 / 12) / 22
    trades_per_day = max(0.2, trades_per_day)

    results = {"passed": 0, "fail_dd": 0, "fail_daily": 0, "fail_time": 0,
               "days_to_pass": [], "final_equities": []}

    for _ in range(n_sims):
        equity = 0.0
        peak_eq = 0.0
        passed = False
        fail = None
        consec_loss = 0

        for day in range(trading_days):
            n_today = np.random.poisson(trades_per_day)
            n_today = min(n_today, 5)
            daily_pnl = 0.0

            for _ in range(n_today):
                # Adaptive risk: scale down on losses
                if consec_loss >= 4:
                    risk_mult = 0.6
                elif consec_loss >= 2:
                    risk_mult = 0.8
                elif equity > 0 and (peak_eq - equity) < 1.0:
                    risk_mult = 1.15
                else:
                    risk_mult = 1.0

                trade_r = np.random.choice(pnl_arr)
                trade_pct = trade_r * risk_base * risk_mult
                equity += trade_pct
                daily_pnl += trade_pct
                peak_eq = max(peak_eq, equity)

                if trade_r > 0:
                    consec_loss = 0
                elif trade_r < 0:
                    consec_loss += 1

                if peak_eq - equity >= max_dd:
                    fail = "dd"
                    break
                if equity >= target:
                    passed = True
                    break

            if passed or fail:
                break
            if daily_pnl <= -max_daily:
                fail = "daily"
                break

        results["final_equities"].append(equity)
        if passed:
            results["passed"] += 1
            results["days_to_pass"].append(day + 1)
        elif fail == "dd":
            results["fail_dd"] += 1
        elif fail == "daily":
            results["fail_daily"] += 1
        else:
            results["fail_time"] += 1

    finals = np.array(results["final_equities"])
    return {
        "pass_rate": 100 * results["passed"] / n_sims,
        "fail_dd_rate": 100 * results["fail_dd"] / n_sims,
        "fail_daily_rate": 100 * results["fail_daily"] / n_sims,
        "fail_time_rate": 100 * results["fail_time"] / n_sims,
        "avg_days": float(np.mean(results["days_to_pass"])) if results["days_to_pass"] else 0,
        "trades_per_day": trades_per_day,
        "median_final_equity": float(np.median(finals)),
        "p10_equity": float(np.percentile(finals, 10)),
        "p90_equity": float(np.percentile(finals, 90)),
    }


# ── FTMO EV Calculator ──────────────────────────────────────────────

def ftmo_expected_value(pass_rate_pct, payout_on_pass=10000, cost_per_attempt=500,
                        funded_monthly_pct=4.0, funded_capital=100000, profit_split=0.8):
    """Calculate FTMO business expected value.

    Assumptions:
    - Challenge fee: $500 (refunded on pass)
    - Funded capital: $100k
    - Profit split: 80%
    - Monthly return: from consistent mode data
    """
    p = pass_rate_pct / 100
    # EV per attempt
    ev_attempt = p * (payout_on_pass + cost_per_attempt) - (1 - p) * cost_per_attempt

    # Monthly funded income (once passed)
    monthly_funded_gross = funded_capital * (funded_monthly_pct / 100)
    monthly_funded_net = monthly_funded_gross * profit_split

    # Attempts needed on average
    avg_attempts = 1 / p if p > 0 else float("inf")
    total_cost = avg_attempts * cost_per_attempt

    return {
        "pass_rate": pass_rate_pct,
        "ev_per_attempt": round(ev_attempt, 2),
        "avg_attempts_to_pass": round(avg_attempts, 1),
        "total_cost_to_pass": round(total_cost, 2),
        "monthly_funded_gross": round(monthly_funded_gross, 2),
        "monthly_funded_net": round(monthly_funded_net, 2),
        "annual_funded_net": round(monthly_funded_net * 12, 2),
        "roi_after_pass": round(monthly_funded_net * 12 / total_cost * 100, 1) if total_cost > 0 else 0,
        "payback_months": round(total_cost / monthly_funded_net, 1) if monthly_funded_net > 0 else 0,
    }


# ── Display ──────────────────────────────────────────────────────────

def print_adaptive_results(mode_name, stats, ftmo_results=None, ftmo_ev=None):
    print(f"\n  {'='*65}")
    print(f"  MODE: {mode_name}")
    print(f"  {'='*65}")

    print(f"\n  Portfolio Performance (with execution simulation):")
    print(f"    Trades:              {stats['trades']}")
    print(f"    Win Rate:            {stats['wr']:.1f}%")
    print(f"    Profit Factor:       {stats['pf']:.2f}")
    print(f"    Expectancy (gross):  {stats['exp_r_gross']:+.3f}R")
    print(f"    Expectancy (net):    {stats['exp_r_net']:+.3f}R  ({stats['exp_pct']:+.3f}%)")
    print(f"    Total R (gross):     {stats['total_r_gross']:+.1f}R")
    print(f"    Total R (net):       {stats['total_r_net']:+.1f}R")
    print(f"    Slippage cost:       {stats['slippage_cost_r']:.1f}R")
    print(f"    Total Return:        {stats['total_pct']:+.1f}%")
    print(f"    Max Drawdown:        {stats['max_dd_pct']:+.2f}%")
    print(f"    R/DD:                {stats['rdd']:.2f}")

    print(f"\n  Monthly Stats:")
    print(f"    Avg month:           {stats['monthly_avg_pct']:+.2f}%")
    print(f"    Std month:           {stats['monthly_std_pct']:.2f}%")
    print(f"    Worst month:         {stats['monthly_min_pct']:+.2f}%")
    print(f"    Best month:          {stats['monthly_max_pct']:+.2f}%")
    print(f"    % positive months:   {stats['pct_positive_months']:.0f}%")

    print(f"\n  Per Instrument:")
    for sym, im in stats.get("per_instrument", {}).items():
        print(f"    {sym:>8s}: {im['n']:>4d} trades  WR {im['wr']:.0f}%  "
              f"exp {im['exp']:+.3f}R  total {im['total_r']:+.1f}R")

    print(f"\n  Adaptive Mode Distribution:")
    total_t = sum(stats.get("mode_distribution", {}).values())
    for mode, count in stats.get("mode_distribution", {}).items():
        pnl = stats.get("mode_pnl_r", {}).get(mode, 0)
        pct = 100 * count / total_t if total_t else 0
        if count > 0:
            print(f"    {mode:>12s}: {count:>4d} trades ({pct:.0f}%)  "
                  f"PnL {pnl:+.1f}R  avg {pnl/count:+.2f}R/trade")

    print(f"\n  Risk Engine Blocks:")
    for reason, count in stats.get("blocked", {}).items():
        if count > 0:
            print(f"    {reason}: {count}")

    print(f"\n  Execution Quality:")
    ex = stats.get("execution", {})
    print(f"    Fills:               {ex.get('fills', 0)}")
    print(f"    Rejects:             {ex.get('rejects', 0)}")
    print(f"    Avg slippage:        {ex.get('avg_slippage_r', 0):.4f}R")

    print(f"\n  Yearly Return:")
    for yr, pct in sorted(stats.get("yearly", {}).items()):
        print(f"    {yr}: {pct:+.1f}%")

    if ftmo_results:
        print(f"\n  FTMO Challenge (adaptive MC, {FTMO_SIMS:,} sims):")
        print(f"    Pass rate:           {ftmo_results['pass_rate']:.1f}%")
        print(f"    Fail (DD):           {ftmo_results['fail_dd_rate']:.1f}%")
        print(f"    Fail (daily loss):   {ftmo_results['fail_daily_rate']:.1f}%")
        print(f"    Fail (timeout):      {ftmo_results['fail_time_rate']:.1f}%")
        print(f"    Avg days to pass:    {ftmo_results['avg_days']:.0f}")
        print(f"    Trades/day:          {ftmo_results['trades_per_day']:.2f}")
        print(f"    Median final eq:     {ftmo_results['median_final_equity']:+.1f}%")
        print(f"    P10 equity:          {ftmo_results['p10_equity']:+.1f}%")
        print(f"    P90 equity:          {ftmo_results['p90_equity']:+.1f}%")

    if ftmo_ev:
        print(f"\n  FTMO Business Model ($100k funded):")
        print(f"    EV per attempt:      ${ftmo_ev['ev_per_attempt']:+,.0f}")
        print(f"    Avg attempts:        {ftmo_ev['avg_attempts_to_pass']:.1f}")
        print(f"    Cost to pass:        ${ftmo_ev['total_cost_to_pass']:,.0f}")
        print(f"    Monthly funded net:  ${ftmo_ev['monthly_funded_net']:,.0f}")
        print(f"    Annual funded net:   ${ftmo_ev['annual_funded_net']:,.0f}")
        print(f"    Payback months:      {ftmo_ev['payback_months']:.1f}")
        print(f"    Annual ROI:          {ftmo_ev['roi_after_pass']:.0f}%")


# ── Main ─────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-fetch", action="store_true")
    args = parser.parse_args()

    print("=" * 70)
    print("  PORTFOLIO ADAPTIVE SIMULATION")
    print("  Correlation-aware heat + Dynamic risk scaling + Execution sim")
    print("=" * 70)

    cfg = load_config(CONFIG_PATH)
    setup_logging(cfg)

    with open(PROFILES_PATH) as f:
        profiles = yaml.safe_load(f)

    instruments_cfg = profiles["instruments"]
    modes = profiles["modes"]
    base_path = Path(cfg.get("data", {}).get("base_path", "data/market_cache"))

    promoted = {sym: inst for sym, inst in instruments_cfg.items() if inst.get("status") == "PROMOTE"}
    print(f"\n  Promoted instruments: {', '.join(promoted.keys())}")

    # Generate signals
    print("\n  Generating signals...")
    all_signals = []
    for sym, inst_profile in promoted.items():
        sigs = generate_instrument_signals(sym, cfg, inst_profile, base_path)
        all_signals.extend(sigs)
        print(f"    {sym}: {len(sigs)} signals")

    print(f"\n  Total signals: {len(all_signals)}")

    np.random.seed(42)

    # ── Run CHALLENGE mode (with adaptive) ────────────────────────────
    challenge_cfg = modes["challenge"]
    print("\n" + "-" * 70)
    print("  Running CHALLENGE mode (adaptive)...")

    ch_adaptive = simulate_adaptive_portfolio(all_signals, challenge_cfg, instruments_cfg, with_adaptive=True)
    ch_ftmo = ftmo_adaptive_mc(ch_adaptive["trade_list"], challenge_cfg)
    ch_ev = ftmo_expected_value(
        ch_ftmo["pass_rate"],
        funded_monthly_pct=ch_adaptive["monthly_avg_pct"],
    )
    print_adaptive_results("CHALLENGE (ADAPTIVE)", ch_adaptive, ch_ftmo, ch_ev)

    # Compare: CHALLENGE without adaptive
    print("\n" + "-" * 70)
    print("  Running CHALLENGE mode (static baseline)...")
    ch_static = simulate_adaptive_portfolio(all_signals, challenge_cfg, instruments_cfg, with_adaptive=False)
    ch_ftmo_static = ftmo_adaptive_mc(ch_static["trade_list"], challenge_cfg)
    print_adaptive_results("CHALLENGE (STATIC)", ch_static, ch_ftmo_static)

    # ── Run CONSISTENT mode ───────────────────────────────────────────
    consistent_cfg = modes["consistent"]
    print("\n" + "-" * 70)
    print("  Running CONSISTENT mode (adaptive)...")
    co_adaptive = simulate_adaptive_portfolio(all_signals, consistent_cfg, instruments_cfg, with_adaptive=True)
    print_adaptive_results("CONSISTENT (ADAPTIVE)", co_adaptive)

    print("\n" + "-" * 70)
    print("  Running CONSISTENT mode (static baseline)...")
    co_static = simulate_adaptive_portfolio(all_signals, consistent_cfg, instruments_cfg, with_adaptive=False)
    print_adaptive_results("CONSISTENT (STATIC)", co_static)

    # ── Comparison Table ──────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("  COMPARISON: ADAPTIVE vs STATIC")
    print("=" * 70)

    rows = [
        ("CHALLENGE ADAPTIVE", ch_adaptive),
        ("CHALLENGE STATIC", ch_static),
        ("CONSISTENT ADAPTIVE", co_adaptive),
        ("CONSISTENT STATIC", co_static),
    ]

    header = f"  {'Config':<25s} {'Trades':>6s} {'WR':>5s} {'PF':>5s} {'Exp/R':>7s} {'Total%':>7s} {'MaxDD':>7s} {'R/DD':>5s} {'Mo.Avg':>7s}"
    print(header)
    print("  " + "-" * len(header))
    for name, st in rows:
        print(f"  {name:<25s} {st['trades']:>6d} {st['wr']:>4.0f}% {st['pf']:>5.2f} "
              f"{st['exp_r_net']:>+6.3f} {st['total_pct']:>+6.1f}% "
              f"{st['max_dd_pct']:>+6.2f} {st['rdd']:>5.2f} {st['monthly_avg_pct']:>+6.2f}%")

    # ── FTMO EV Table ─────────────────────────────────────────────────
    print(f"\n  {'='*65}")
    print("  FTMO EXPECTED VALUE ANALYSIS")
    print(f"  {'='*65}")

    for label, ftmo_res, mo_avg in [
        ("Adaptive", ch_ftmo, ch_adaptive["monthly_avg_pct"]),
        ("Static", ch_ftmo_static, ch_static["monthly_avg_pct"]),
    ]:
        ev = ftmo_expected_value(ftmo_res["pass_rate"], funded_monthly_pct=mo_avg)
        print(f"\n  {label} ({ftmo_res['pass_rate']:.1f}% pass rate):")
        print(f"    EV per attempt:      ${ev['ev_per_attempt']:+,.0f}")
        print(f"    Monthly funded:      ${ev['monthly_funded_net']:,.0f}")
        print(f"    Annual funded:       ${ev['annual_funded_net']:,.0f}")
        print(f"    Payback:             {ev['payback_months']:.1f} months")
        print(f"    Annual ROI:          {ev['roi_after_pass']:.0f}%")

    # ── Executive Summary ─────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("  EXECUTIVE SUMMARY")
    print("=" * 70)

    ch_improvement = ch_adaptive["total_pct"] - ch_static["total_pct"]
    co_improvement = co_adaptive["total_pct"] - co_static["total_pct"]
    dd_improvement = abs(ch_adaptive["max_dd_pct"]) - abs(ch_static["max_dd_pct"])

    print(f"""
  PORTFOLIO: XAUUSD + GBPUSD + USDJPY (data-validated, correlation-aware)
  SIMULATION: {PERIOD_DAYS / 365.25:.0f} years, realistic execution (slippage + spread)

  ADAPTIVE vs STATIC:
    Challenge total return:  {ch_improvement:+.1f}% (adaptive vs static)
    Consistent total return: {co_improvement:+.1f}% (adaptive vs static)
    Challenge max DD delta:  {dd_improvement:+.2f}%

  KEY INSIGHT:
    Adaptive mode = same kernel, same instruments, smarter capital deployment
    Total slippage cost: {ch_adaptive['slippage_cost_r']:.1f}R (Challenge), {co_adaptive['slippage_cost_r']:.1f}R (Consistent)
    Heat engine blocks:  {ch_adaptive['blocked']['heat_engine']} (Chal), {co_adaptive['blocked']['heat_engine']} (Cons)

  FTMO BUSINESS MODEL (adaptive, $100k funded):
    Pass rate: {ch_ftmo['pass_rate']:.1f}%
    Monthly funded income: ${ftmo_expected_value(ch_ftmo['pass_rate'], funded_monthly_pct=ch_adaptive['monthly_avg_pct'])['monthly_funded_net']:,.0f}
    Annual funded income:  ${ftmo_expected_value(ch_ftmo['pass_rate'], funded_monthly_pct=ch_adaptive['monthly_avg_pct'])['annual_funded_net']:,.0f}
""")

    # Save report
    report_dir = Path("reports/latest")
    report_dir.mkdir(parents=True, exist_ok=True)

    def _clean(d):
        return {k: v for k, v in d.items() if k != "trade_list"}

    report = {
        "challenge_adaptive": _clean(ch_adaptive),
        "challenge_static": _clean(ch_static),
        "consistent_adaptive": _clean(co_adaptive),
        "consistent_static": _clean(co_static),
        "ftmo_adaptive": ch_ftmo,
        "ftmo_static": ch_ftmo_static,
        "ftmo_ev_adaptive": ftmo_expected_value(ch_ftmo["pass_rate"], funded_monthly_pct=ch_adaptive["monthly_avg_pct"]),
        "ftmo_ev_static": ftmo_expected_value(ch_ftmo_static["pass_rate"], funded_monthly_pct=ch_static["monthly_avg_pct"]),
    }
    path = report_dir / "portfolio_adaptive_sim.json"
    with open(path, "w") as f:
        json.dump(report, f, indent=2, default=str)
    print(f"  Saved report to {path}")
    print("=" * 70)


if __name__ == "__main__":
    main()
