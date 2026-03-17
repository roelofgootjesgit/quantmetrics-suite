"""
Portfolio Dual-Mode Simulation.

Two distinct trading modes on the same 3-instrument portfolio:

MODE 1 — CHALLENGE (FTMO)
  Target: 10% in 30 days, max 5% daily loss, max 10% total DD
  Risk: 1.5% per trade, max 6% portfolio heat

MODE 2 — CONSISTENT
  Target: 3-6% monthly, low drawdown
  Risk: 0.75% per trade, max 3% portfolio heat

Both modes use:
  - Instrument-specific regime gates (GBPUSD expansion OFF)
  - Portfolio-level risk engine (heat limits, correlation guard)
  - Dynamic exits per regime
  - FTMO pass probability via Monte Carlo

Usage:
    python scripts/portfolio_dual_mode.py
    python scripts/portfolio_dual_mode.py --skip-fetch
"""
import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
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

PERIOD_DAYS = 1825
CONFIG_PATH = "configs/strict_prod_v2.yaml"
PROFILES_PATH = "configs/instruments/instrument_profiles.yaml"
FTMO_SIMS = 10_000


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


# ── Generate Signals Per Instrument ───────────────────────────────────

def generate_instrument_signals(symbol, cfg, inst_profile, base_path):
    """Run kernel with instrument-specific regime gates."""
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

    # Instrument-specific regime gates
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

            # Instrument-specific regime gate
            if not inst_regimes.get(regime, False):
                continue

            # V2 regime profile filtering (session/time)
            rp = regime_profiles.get(regime, {})
            if rp.get("skip", False):
                continue

            # Expansion session/time filter (from base config or instrument)
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
            signals.append({
                "ts": ts, "symbol": symbol, "direction": direction,
                "regime": regime, "session": session, "pnl": pnl,
            })

    return signals


# ── Portfolio Risk Engine ─────────────────────────────────────────────

class PortfolioRiskEngine:
    """Enforces portfolio-level risk constraints."""

    def __init__(self, mode_cfg):
        self.risk_per_trade = mode_cfg.get("risk_per_trade_pct", 1.0)
        self.max_daily_loss = mode_cfg.get("max_daily_loss_pct", 5.0)
        self.max_total_dd = mode_cfg.get("max_total_dd_pct", 10.0)
        self.max_heat = mode_cfg.get("max_portfolio_heat_pct", 6.0)
        self.max_correlated = mode_cfg.get("max_correlated_exposure", 2)

    def check_trade(self, equity_pct, daily_pnl_pct, open_heat_pct, same_class_count):
        """Return (allowed, reason)."""
        if daily_pnl_pct <= -self.max_daily_loss:
            return False, "daily_loss_limit"
        dd_from_peak = -equity_pct if equity_pct < 0 else 0
        if dd_from_peak >= self.max_total_dd:
            return False, "total_dd_limit"
        if open_heat_pct + self.risk_per_trade > self.max_heat:
            return False, f"heat_limit ({open_heat_pct:.1f}% + {self.risk_per_trade}% > {self.max_heat}%)"
        if same_class_count >= self.max_correlated:
            return False, f"correlated_exposure ({same_class_count} >= {self.max_correlated})"
        return True, "ok"


# ── Portfolio Simulation ──────────────────────────────────────────────

def simulate_portfolio(all_signals, mode_cfg, instruments_cfg):
    """Simulate portfolio with risk engine. Returns daily equity curve + stats."""
    risk_engine = PortfolioRiskEngine(mode_cfg)
    risk_pct = mode_cfg["risk_per_trade_pct"]

    # Merge all signals and sort by timestamp
    merged = sorted(all_signals, key=lambda s: s["ts"])

    equity_pct = 0.0
    peak_equity = 0.0
    daily_pnl = {}
    trades = []
    blocked = {"daily_loss": 0, "total_dd": 0, "heat_limit": 0, "correlated_exposure": 0}
    open_positions = []  # simplified tracking

    for sig in merged:
        ts = sig["ts"]
        day = ts.date() if hasattr(ts, "date") else ts
        sym = sig["symbol"]
        inst = instruments_cfg.get(sym, {})
        asset_class = inst.get("asset_class", "unknown")
        risk_mult = inst.get("risk_multiplier", 1.0)

        # Daily reset
        day_pnl = daily_pnl.get(day, 0.0)

        # Count same-class open exposure
        same_class = sum(1 for p in open_positions if p["asset_class"] == asset_class)
        open_heat = len(open_positions) * risk_pct

        allowed, reason = risk_engine.check_trade(equity_pct, day_pnl, open_heat, same_class)
        if not allowed:
            key = reason.split(" ")[0].split("(")[0]
            blocked[key] = blocked.get(key, 0) + 1
            continue

        # Execute trade
        trade_risk = risk_pct * risk_mult
        trade_pnl_pct = sig["pnl"] * trade_risk
        equity_pct += trade_pnl_pct
        peak_equity = max(peak_equity, equity_pct)
        daily_pnl[day] = daily_pnl.get(day, 0.0) + trade_pnl_pct

        trades.append({
            "ts": ts, "symbol": sym, "regime": sig["regime"],
            "pnl_r": sig["pnl"], "pnl_pct": trade_pnl_pct,
            "equity_after": equity_pct,
        })

    # Compute stats
    if not trades:
        return {"error": "no_trades"}

    pnl_arr = np.array([t["pnl_r"] for t in trades])
    pct_arr = np.array([t["pnl_pct"] for t in trades])
    wins = pnl_arr[pnl_arr > 0]
    losses = pnl_arr[pnl_arr < 0]
    gw = wins.sum() if len(wins) else 0
    gl = abs(losses.sum()) if len(losses) else 0

    eq_curve = np.array([t["equity_after"] for t in trades])
    peak = np.maximum.accumulate(eq_curve)
    dd = eq_curve - peak
    max_dd_pct = float(dd.min())

    # Monthly breakdown
    monthly = {}
    for t in trades:
        mo = t["ts"].strftime("%Y-%m") if hasattr(t["ts"], "strftime") else str(t["ts"])[:7]
        monthly.setdefault(mo, 0.0)
        monthly[mo] += t["pnl_pct"]

    monthly_vals = list(monthly.values())

    # Per-instrument breakdown
    per_inst = {}
    for t in trades:
        sym = t["symbol"]
        per_inst.setdefault(sym, [])
        per_inst[sym].append(t["pnl_r"])

    # Yearly
    yearly = {}
    for t in trades:
        yr = t["ts"].year if hasattr(t["ts"], "year") else 2025
        yearly.setdefault(yr, 0.0)
        yearly[yr] += t["pnl_pct"]

    return {
        "trades": len(trades),
        "total_pct": float(equity_pct),
        "total_r": float(pnl_arr.sum()),
        "wr": float(100 * len(wins) / len(pnl_arr)),
        "pf": float(gw / gl) if gl else 0,
        "exp_r": float(pnl_arr.mean()),
        "exp_pct": float(pct_arr.mean()),
        "max_dd_pct": max_dd_pct,
        "rdd": float(equity_pct / abs(max_dd_pct)) if max_dd_pct < 0 else 0,
        "monthly_avg_pct": float(np.mean(monthly_vals)) if monthly_vals else 0,
        "monthly_std_pct": float(np.std(monthly_vals)) if monthly_vals else 0,
        "monthly_min_pct": float(np.min(monthly_vals)) if monthly_vals else 0,
        "monthly_max_pct": float(np.max(monthly_vals)) if monthly_vals else 0,
        "pct_positive_months": float(100 * sum(1 for m in monthly_vals if m > 0) / len(monthly_vals)) if monthly_vals else 0,
        "blocked": blocked,
        "yearly": yearly,
        "per_instrument": {
            sym: {
                "n": len(pnls), "exp": float(np.mean(pnls)),
                "total_r": float(np.sum(pnls)),
                "wr": float(100 * sum(1 for p in pnls if p > 0) / len(pnls)),
            } for sym, pnls in per_inst.items()
        },
        "trade_list": trades,
    }


# ── FTMO Monte Carlo ─────────────────────────────────────────────────

def ftmo_monte_carlo(trade_pnls, mode_cfg, n_sims=FTMO_SIMS):
    """Simulate FTMO challenge attempts."""
    target = mode_cfg.get("target_pct", 10.0)
    max_daily = mode_cfg.get("max_daily_loss_pct", 5.0)
    max_dd = mode_cfg.get("max_total_dd_pct", 10.0)
    risk = mode_cfg.get("risk_per_trade_pct", 1.5)
    trading_days = 30

    # Estimate trades per day
    n_trades = len(trade_pnls)
    trades_per_day = n_trades / (PERIOD_DAYS / 365.25 * 252 / 12) / 22
    trades_per_day = max(0.2, trades_per_day)

    pnl_arr = np.array(trade_pnls)
    results = {"passed": 0, "fail_dd": 0, "fail_daily": 0, "fail_time": 0, "days_to_pass": []}

    for _ in range(n_sims):
        equity = 0.0
        peak_eq = 0.0
        passed = False
        fail = None

        for day in range(trading_days):
            n_today = np.random.poisson(trades_per_day)
            n_today = min(n_today, 5)
            daily_pnl = 0.0

            for _ in range(n_today):
                trade_r = np.random.choice(pnl_arr)
                trade_pct = trade_r * risk
                equity += trade_pct
                daily_pnl += trade_pct
                peak_eq = max(peak_eq, equity)

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

        if passed:
            results["passed"] += 1
            results["days_to_pass"].append(day + 1)
        elif fail == "dd":
            results["fail_dd"] += 1
        elif fail == "daily":
            results["fail_daily"] += 1
        else:
            results["fail_time"] += 1

    return {
        "pass_rate": 100 * results["passed"] / n_sims,
        "fail_dd_rate": 100 * results["fail_dd"] / n_sims,
        "fail_daily_rate": 100 * results["fail_daily"] / n_sims,
        "fail_time_rate": 100 * results["fail_time"] / n_sims,
        "avg_days": float(np.mean(results["days_to_pass"])) if results["days_to_pass"] else 0,
        "trades_per_day": trades_per_day,
    }


# ── Display ───────────────────────────────────────────────────────────

def print_mode_results(mode_name, stats, ftmo_results=None):
    print(f"\n  {'='*60}")
    print(f"  MODE: {mode_name}")
    print(f"  {'='*60}")

    print(f"\n  Portfolio Performance:")
    print(f"    Trades:              {stats['trades']}")
    print(f"    Win Rate:            {stats['wr']:.1f}%")
    print(f"    Profit Factor:       {stats['pf']:.2f}")
    print(f"    Expectancy:          {stats['exp_r']:+.3f}R  ({stats['exp_pct']:+.3f}%)")
    print(f"    Total Return:        {stats['total_pct']:+.1f}%  ({stats['total_r']:+.1f}R)")
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
        print(f"    {sym:>8s}: {im['n']:>4d} trades  WR {im['wr']:.0f}%  exp {im['exp']:+.3f}R  total {im['total_r']:+.1f}R")

    print(f"\n  Risk Engine Blocks:")
    for reason, count in stats.get("blocked", {}).items():
        if count > 0:
            print(f"    {reason}: {count}")

    print(f"\n  Yearly Return:")
    for yr, pct in sorted(stats.get("yearly", {}).items()):
        print(f"    {yr}: {pct:+.1f}%")

    if ftmo_results:
        print(f"\n  FTMO Challenge Probability ({FTMO_SIMS:,} simulations):")
        print(f"    Pass rate:           {ftmo_results['pass_rate']:.1f}%")
        print(f"    Fail (DD):           {ftmo_results['fail_dd_rate']:.1f}%")
        print(f"    Fail (daily loss):   {ftmo_results['fail_daily_rate']:.1f}%")
        print(f"    Fail (timeout):      {ftmo_results['fail_time_rate']:.1f}%")
        print(f"    Avg days to pass:    {ftmo_results['avg_days']:.0f}")
        print(f"    Trades/day:          {ftmo_results['trades_per_day']:.2f}")


# ── Main ──────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-fetch", action="store_true")
    args = parser.parse_args()

    print("=" * 70)
    print("  PORTFOLIO DUAL-MODE SIMULATION")
    print("  CHALLENGE (FTMO) + CONSISTENT")
    print("=" * 70)

    cfg = load_config(CONFIG_PATH)
    setup_logging(cfg)

    with open(PROFILES_PATH) as f:
        profiles = yaml.safe_load(f)

    instruments_cfg = profiles["instruments"]
    modes = profiles["modes"]
    base_path = Path(cfg.get("data", {}).get("base_path", "data/market_cache"))

    # Only promoted instruments
    promoted = {sym: inst for sym, inst in instruments_cfg.items() if inst.get("status") == "PROMOTE"}
    print(f"\n  Promoted instruments: {', '.join(promoted.keys())}")

    # Generate signals for each instrument
    print("\n  Generating signals...")
    all_signals = []
    for sym, inst_profile in promoted.items():
        sigs = generate_instrument_signals(sym, cfg, inst_profile, base_path)
        all_signals.extend(sigs)
        print(f"    {sym}: {len(sigs)} signals ({inst_profile.get('label', '')})")

    print(f"\n  Total signals: {len(all_signals)}")

    # Run both modes
    np.random.seed(42)

    for mode_name, mode_cfg in modes.items():
        stats = simulate_portfolio(all_signals, mode_cfg, instruments_cfg)

        # FTMO Monte Carlo for challenge mode
        ftmo = None
        if mode_name == "challenge":
            trade_pnls = [s["pnl"] for s in all_signals]
            ftmo = ftmo_monte_carlo(trade_pnls, mode_cfg)

            # Also test with slippage
            print(f"\n  FTMO Slippage Sensitivity (Challenge mode):")
            for slip in [0.0, 0.1, 0.2]:
                adj_pnls = [p - slip for p in trade_pnls]
                fres = ftmo_monte_carlo(adj_pnls, mode_cfg)
                print(f"    +{slip:.1f}R slip: pass {fres['pass_rate']:.1f}%, "
                      f"fail_dd {fres['fail_dd_rate']:.1f}%, avg {fres['avg_days']:.0f}d")

        print_mode_results(mode_name.upper(), stats, ftmo)

    # ── Executive Summary ─────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("  EXECUTIVE SUMMARY")
    print("=" * 70)

    challenge_stats = simulate_portfolio(all_signals, modes["challenge"], instruments_cfg)
    consistent_stats = simulate_portfolio(all_signals, modes["consistent"], instruments_cfg)
    challenge_ftmo = ftmo_monte_carlo([s["pnl"] for s in all_signals], modes["challenge"])

    print(f"""
  INSTRUMENTS: XAUUSD + GBPUSD + USDJPY (data-validated portfolio)

  CHALLENGE MODE (FTMO):
    Risk/trade: 1.5%  |  Max heat: 6%
    Monthly avg: {challenge_stats['monthly_avg_pct']:+.2f}%
    Max DD: {challenge_stats['max_dd_pct']:+.2f}%
    FTMO pass rate: {challenge_ftmo['pass_rate']:.1f}%
    Avg days to pass: {challenge_ftmo['avg_days']:.0f}

  CONSISTENT MODE:
    Risk/trade: 0.75%  |  Max heat: 3%
    Monthly avg: {consistent_stats['monthly_avg_pct']:+.2f}%
    Max DD: {consistent_stats['max_dd_pct']:+.2f}%
    Annual return: {consistent_stats['total_pct'] / (PERIOD_DAYS / 365.25):+.1f}%/yr

  BOTH MODES: same kernel, same instruments, different risk envelope
""")

    # Save
    report_dir = Path("reports/latest")
    report_dir.mkdir(parents=True, exist_ok=True)
    report = {
        "challenge": {k: v for k, v in challenge_stats.items() if k != "trade_list"},
        "consistent": {k: v for k, v in consistent_stats.items() if k != "trade_list"},
        "ftmo_challenge": challenge_ftmo,
    }
    path = report_dir / "portfolio_dual_mode.json"
    with open(path, "w") as f:
        json.dump(report, f, indent=2, default=str)
    print(f"  Saved to {path}")
    print("=" * 70)


if __name__ == "__main__":
    main()
