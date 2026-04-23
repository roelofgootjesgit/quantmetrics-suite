"""
Robustness & FTMO Pass Probability Model.

1. Slippage stress test: 0R, 0.1R, 0.2R, 0.3R, 0.5R cost per trade
2. FTMO pass probability model via Monte Carlo:
   - 10% target in 30 trading days
   - 5% max daily loss
   - 10% max total drawdown
   - Simulates 10,000 challenge attempts

Usage:
    python scripts/robustness_and_ftmo.py
"""
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np

from src.quantbuild.config import load_config
from src.quantbuild.logging_config import setup_logging
from src.quantbuild.backtest.engine import (
    _deep_merge, _prepare_sim_cache, _apply_h1_gate,
)
from src.quantbuild.data.sessions import session_from_timestamp
from src.quantbuild.io.parquet_loader import load_parquet, ensure_data
from src.quantbuild.strategies.sqe_xauusd import (
    run_sqe_conditions, get_sqe_default_config, _compute_modules_once,
)
from src.quantbuild.strategy_modules.regime.detector import (
    RegimeDetector, REGIME_TREND, REGIME_EXPANSION, REGIME_COMPRESSION,
)

PERIOD_DAYS = 1825
CONFIG_PATH = "configs/strict_prod_v2.yaml"
FTMO_SIMULATIONS = 10_000


# ── Exit functions (copied from production_analysis) ──────────────────

def _full_excursion(cache, i, direction, max_bars=200):
    close_arr, high_arr, low_arr, ts_arr = cache["close"], cache["high"], cache["low"], cache["ts"]
    n = len(close_arr)
    entry = float(close_arr[i])
    atr = float(cache["atr"][i])
    risk = atr if atr > 0 else entry * 0.005
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


def exit_partial_trail(exc, sl_r=1.0, partial_at=1.0, trail_r=1.5):
    partial_filled = False
    peak = 0.0
    for fav, adv in exc:
        if not partial_filled:
            if adv >= sl_r:
                return -sl_r
            if fav >= partial_at:
                partial_filled = True
                peak = fav
                continue
        else:
            peak = max(peak, fav)
            drawback = peak - fav
            if drawback >= trail_r or adv >= 0:
                trail_exit = max(0, peak - trail_r)
                return partial_at * 0.5 + trail_exit * 0.5
    if partial_filled:
        return max(0, partial_at * 0.5 + (peak - trail_r) * 0.5)
    return 0.0


def exit_dynamic(exc, is_exp_ny):
    """Production exit: baseline for EXP_NY, partial trail for TREND."""
    if is_exp_ny:
        return exit_baseline(exc, tp_r=2.0, sl_r=1.0)
    else:
        return exit_partial_trail(exc, sl_r=1.0, partial_at=1.0, trail_r=1.5)


# ── Metrics helper ────────────────────────────────────────────────────

def compute_metrics(pnl_list):
    if not pnl_list:
        return {"n": 0, "total_r": 0, "wr": 0, "exp": 0, "pf": 0, "max_dd": 0}
    arr = np.array(pnl_list)
    wins = arr[arr > 0]
    losses = arr[arr < 0]
    gw = wins.sum() if len(wins) else 0
    gl = abs(losses.sum()) if len(losses) else 0
    pf = (gw / gl) if gl else (gw or 0)
    cum = np.cumsum(arr)
    peak = np.maximum.accumulate(cum)
    dd = peak - cum
    return {
        "n": len(arr), "total_r": float(arr.sum()),
        "wr": float(100 * len(wins) / len(arr)),
        "exp": float(arr.mean()), "pf": float(pf),
        "max_dd": float(-dd.max()) if len(dd) else 0,
    }


# ── FTMO Monte Carlo Simulator ───────────────────────────────────────

def simulate_ftmo_challenge(
    pnl_array,
    target_pct=10.0,
    max_daily_loss_pct=5.0,
    max_total_dd_pct=10.0,
    risk_per_trade_pct=1.0,
    trading_days=30,
    trades_per_day=None,
    n_simulations=10000,
):
    """
    Simulate FTMO challenge attempts.

    Each simulation:
    - Randomly samples trades from pnl_array
    - Distributes across trading_days
    - Checks daily loss limit and total DD limit
    - Checks if target is reached within time
    """
    n_trades = len(pnl_array)
    if trades_per_day is None:
        # Estimate from actual frequency
        trades_per_day_avg = n_trades / (PERIOD_DAYS / 365.25 * 252 / 12)  # per trading day per month
        trades_per_day = max(0.3, trades_per_day_avg)

    results = {
        "passed": 0, "failed_dd": 0, "failed_daily": 0, "failed_time": 0,
        "days_to_pass": [], "final_equity": [], "max_dd_pct": [],
        "max_daily_loss_pct": [],
    }

    for _ in range(n_simulations):
        equity = 0.0
        peak_equity = 0.0
        passed = False
        fail_reason = None

        for day in range(trading_days):
            # Random number of trades this day (Poisson-ish)
            n_today = np.random.poisson(trades_per_day)
            n_today = min(n_today, 5)  # cap at 5 trades per day
            daily_pnl = 0.0

            for _ in range(n_today):
                trade_r = np.random.choice(pnl_array)
                trade_pct = trade_r * risk_per_trade_pct
                equity += trade_pct
                daily_pnl += trade_pct

                peak_equity = max(peak_equity, equity)

                # Check total DD
                dd_from_peak = peak_equity - equity
                if dd_from_peak >= max_total_dd_pct:
                    fail_reason = "total_dd"
                    break

                # Check target
                if equity >= target_pct:
                    passed = True
                    break

            if passed or fail_reason:
                break

            # Check daily loss
            if daily_pnl <= -max_daily_loss_pct:
                fail_reason = "daily_loss"
                break

        if passed:
            results["passed"] += 1
            results["days_to_pass"].append(day + 1)
        elif fail_reason == "total_dd":
            results["failed_dd"] += 1
        elif fail_reason == "daily_loss":
            results["failed_daily"] += 1
        else:
            results["failed_time"] += 1

        results["final_equity"].append(equity)
        results["max_dd_pct"].append(peak_equity - min(equity, 0) if peak_equity > equity else 0)

    return results


# ── Main ──────────────────────────────────────────────────────────────

def main():
    print("=" * 70)
    print("  ROBUSTNESS & FTMO PASS PROBABILITY MODEL")
    print("=" * 70)

    cfg = load_config(CONFIG_PATH)
    setup_logging(cfg)

    symbol = cfg.get("symbol", "XAUUSD")
    base_path = Path(cfg.get("data", {}).get("base_path", "data/market_cache"))
    session_mode = cfg["backtest"].get("session_mode", "extended")

    end = datetime.now()
    start = end - timedelta(days=PERIOD_DAYS)
    data = load_parquet(base_path, symbol, "15m", start=start, end=end).sort_index()
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

    # Build V2 signals
    signals = []
    for i in range(1, len(data) - 1):
        for direction, mask in [("LONG", long_e), ("SHORT", short_e)]:
            if not mask.iloc[i]:
                continue
            ts = data.index[i]
            regime = regime_series.iloc[i] if i < len(regime_series) else None
            session = session_from_timestamp(ts, mode=session_mode)
            rp = regime_profiles.get(regime, {}) if regime else {}
            if rp.get("skip", False):
                continue
            allowed = rp.get("allowed_sessions")
            if allowed and session not in allowed:
                continue
            min_h = rp.get("min_hour_utc")
            if min_h is not None and ts.hour < min_h:
                continue
            exc = _full_excursion(sim_cache, i, direction)
            is_exp_ny = (regime == REGIME_EXPANSION and session in ("New York", "Overlap") and ts.hour >= 10)
            signals.append({"exc": exc, "is_exp_ny": is_exp_ny})

    # Compute base PnL (no slippage)
    base_pnl = [exit_dynamic(s["exc"], s["is_exp_ny"]) for s in signals]

    print(f"\n  V2 signals: {len(signals)}")
    print(f"  Base expectancy: {np.mean(base_pnl):.3f}R")

    # =========================================================
    # SECTION 1: SLIPPAGE STRESS TEST
    # =========================================================
    print("\n" + "=" * 70)
    print("  SECTION 1: SLIPPAGE STRESS TEST")
    print("=" * 70)

    slippage_levels = [0.0, 0.05, 0.1, 0.15, 0.2, 0.25, 0.3, 0.4, 0.5]

    header = (f"  {'Slip':>6s} {'N':>4s} {'WR':>6s} {'PF':>6s} {'Exp':>7s} "
              f"{'TotalR':>8s} {'MaxDD':>7s} {'R/DD':>6s} {'Robust':>7s}")
    print(header)
    print("  " + "-" * (len(header) - 2))

    for slip in slippage_levels:
        adjusted = [p - slip for p in base_pnl]
        m = compute_metrics(adjusted)
        rdd = m["total_r"] / abs(m["max_dd"]) if m["max_dd"] else 0
        robust = "OK" if m["exp"] > 0.25 else ("MARGINAL" if m["exp"] > 0.1 else "FAIL")
        print(f"  {slip:>5.2f}R {m['n']:>4d} {m['wr']:>5.1f}% {m['pf']:>6.2f} "
              f"{m['exp']:>+6.3f}R {m['total_r']:>+7.1f}R {m['max_dd']:>+6.1f}R "
              f"{rdd:>5.2f}  {robust}")

    # Break-even slippage
    total = sum(base_pnl)
    breakeven_slip = total / len(base_pnl) if base_pnl else 0
    print(f"\n  Break-even slippage: {breakeven_slip:.3f}R per trade")
    print(f"  At 0.2R slippage: expectancy = {np.mean(base_pnl) - 0.2:.3f}R -> {'ROBUST' if np.mean(base_pnl) - 0.2 > 0.25 else 'MARGINAL' if np.mean(base_pnl) - 0.2 > 0.1 else 'FAIL'}")
    print(f"  At 0.3R slippage: expectancy = {np.mean(base_pnl) - 0.3:.3f}R -> {'ROBUST' if np.mean(base_pnl) - 0.3 > 0.25 else 'MARGINAL' if np.mean(base_pnl) - 0.3 > 0.1 else 'FAIL'}")

    # =========================================================
    # SECTION 2: FTMO PASS PROBABILITY — SINGLE INSTRUMENT
    # =========================================================
    print("\n" + "=" * 70)
    print(f"  SECTION 2: FTMO PASS PROBABILITY ({FTMO_SIMULATIONS:,} simulations)")
    print("=" * 70)

    pnl_arr = np.array(base_pnl)
    trades_per_year = len(pnl_arr) / (PERIOD_DAYS / 365.25)
    trades_per_month = trades_per_year / 12
    trades_per_day = trades_per_month / 22  # ~22 trading days per month

    print(f"\n  Trade frequency: {trades_per_year:.0f}/yr = {trades_per_month:.1f}/mo = {trades_per_day:.2f}/day")

    np.random.seed(42)

    print(f"\n  SINGLE INSTRUMENT (XAUUSD):")
    print(f"  {'Risk%':>6s} {'Pass%':>7s} {'Fail DD':>8s} {'Fail Daily':>11s} {'Timeout':>8s} "
          f"{'AvgDays':>8s} {'MedEquity':>10s}")
    print("  " + "-" * 65)

    for risk_pct in [0.5, 0.75, 1.0, 1.25, 1.5, 2.0]:
        res = simulate_ftmo_challenge(
            pnl_arr,
            target_pct=10.0, max_daily_loss_pct=5.0, max_total_dd_pct=10.0,
            risk_per_trade_pct=risk_pct, trading_days=30,
            trades_per_day=trades_per_day,
            n_simulations=FTMO_SIMULATIONS,
        )
        pass_rate = 100 * res["passed"] / FTMO_SIMULATIONS
        fail_dd = 100 * res["failed_dd"] / FTMO_SIMULATIONS
        fail_daily = 100 * res["failed_daily"] / FTMO_SIMULATIONS
        fail_time = 100 * res["failed_time"] / FTMO_SIMULATIONS
        avg_days = np.mean(res["days_to_pass"]) if res["days_to_pass"] else 0
        med_eq = np.median(res["final_equity"])
        print(f"  {risk_pct:>5.1f}% {pass_rate:>6.1f}% {fail_dd:>7.1f}% {fail_daily:>10.1f}% "
              f"{fail_time:>7.1f}% {avg_days:>7.1f}d {med_eq:>+9.1f}%")

    # =========================================================
    # SECTION 3: FTMO — PORTFOLIO (5 instruments)
    # =========================================================
    print("\n" + "=" * 70)
    print("  SECTION 3: FTMO PASS PROBABILITY — PORTFOLIO (5 instruments)")
    print("=" * 70)

    # Scale trade frequency by 5, apply conservative edge reduction
    instrument_factors = [1.0, 0.85, 0.65, 0.70, 0.75]
    portfolio_pnl = []
    for factor in instrument_factors:
        for p in base_pnl:
            portfolio_pnl.append(p * factor)

    portfolio_arr = np.array(portfolio_pnl)
    port_trades_per_day = trades_per_day * len(instrument_factors)

    print(f"\n  Portfolio frequency: {port_trades_per_day:.1f} trades/day across 5 instruments")
    print(f"  Portfolio expectancy: {portfolio_arr.mean():.3f}R")

    print(f"\n  {'Risk%':>6s} {'Pass%':>7s} {'Fail DD':>8s} {'Fail Daily':>11s} {'Timeout':>8s} "
          f"{'AvgDays':>8s} {'MedEquity':>10s}")
    print("  " + "-" * 65)

    best_risk = 0
    best_pass = 0

    for risk_pct in [0.25, 0.5, 0.75, 1.0, 1.25, 1.5]:
        res = simulate_ftmo_challenge(
            portfolio_arr,
            target_pct=10.0, max_daily_loss_pct=5.0, max_total_dd_pct=10.0,
            risk_per_trade_pct=risk_pct, trading_days=30,
            trades_per_day=port_trades_per_day,
            n_simulations=FTMO_SIMULATIONS,
        )
        pass_rate = 100 * res["passed"] / FTMO_SIMULATIONS
        fail_dd = 100 * res["failed_dd"] / FTMO_SIMULATIONS
        fail_daily = 100 * res["failed_daily"] / FTMO_SIMULATIONS
        fail_time = 100 * res["failed_time"] / FTMO_SIMULATIONS
        avg_days = np.mean(res["days_to_pass"]) if res["days_to_pass"] else 0
        med_eq = np.median(res["final_equity"])
        print(f"  {risk_pct:>5.2f}% {pass_rate:>6.1f}% {fail_dd:>7.1f}% {fail_daily:>10.1f}% "
              f"{fail_time:>7.1f}% {avg_days:>7.1f}d {med_eq:>+9.1f}%")

        if pass_rate > best_pass:
            best_pass = pass_rate
            best_risk = risk_pct

    # =========================================================
    # SECTION 4: FTMO — WITH SLIPPAGE
    # =========================================================
    print("\n" + "=" * 70)
    print("  SECTION 4: FTMO PASS RATE WITH SLIPPAGE (portfolio, best risk)")
    print("=" * 70)

    for slip in [0.0, 0.1, 0.2, 0.3]:
        adj_pnl = portfolio_arr - slip
        res = simulate_ftmo_challenge(
            adj_pnl,
            target_pct=10.0, max_daily_loss_pct=5.0, max_total_dd_pct=10.0,
            risk_per_trade_pct=best_risk, trading_days=30,
            trades_per_day=port_trades_per_day,
            n_simulations=FTMO_SIMULATIONS,
        )
        pass_rate = 100 * res["passed"] / FTMO_SIMULATIONS
        fail_dd = 100 * res["failed_dd"] / FTMO_SIMULATIONS
        avg_days = np.mean(res["days_to_pass"]) if res["days_to_pass"] else 0
        print(f"  Slippage {slip:.1f}R @ {best_risk}% risk: "
              f"pass {pass_rate:.1f}%, fail_dd {fail_dd:.1f}%, avg {avg_days:.0f}d")

    # =========================================================
    # SECTION 5: EXECUTIVE SUMMARY
    # =========================================================
    print("\n" + "=" * 70)
    print("  EXECUTIVE SUMMARY")
    print("=" * 70)

    # Recompute for summary
    base_m = compute_metrics(base_pnl)
    slip02 = compute_metrics([p - 0.2 for p in base_pnl])
    slip03 = compute_metrics([p - 0.3 for p in base_pnl])

    # Best FTMO single-instrument
    single_best_res = simulate_ftmo_challenge(
        pnl_arr, target_pct=10.0, max_daily_loss_pct=5.0, max_total_dd_pct=10.0,
        risk_per_trade_pct=1.0, trading_days=30, trades_per_day=trades_per_day,
        n_simulations=FTMO_SIMULATIONS,
    )
    single_pass = 100 * single_best_res["passed"] / FTMO_SIMULATIONS

    # Best FTMO portfolio
    port_best_res = simulate_ftmo_challenge(
        portfolio_arr, target_pct=10.0, max_daily_loss_pct=5.0, max_total_dd_pct=10.0,
        risk_per_trade_pct=best_risk, trading_days=30, trades_per_day=port_trades_per_day,
        n_simulations=FTMO_SIMULATIONS,
    )
    port_pass = 100 * port_best_res["passed"] / FTMO_SIMULATIONS
    port_avg_days = np.mean(port_best_res["days_to_pass"]) if port_best_res["days_to_pass"] else 0

    # With 0.2R slippage
    port_slip_res = simulate_ftmo_challenge(
        portfolio_arr - 0.2, target_pct=10.0, max_daily_loss_pct=5.0, max_total_dd_pct=10.0,
        risk_per_trade_pct=best_risk, trading_days=30, trades_per_day=port_trades_per_day,
        n_simulations=FTMO_SIMULATIONS,
    )
    port_slip_pass = 100 * port_slip_res["passed"] / FTMO_SIMULATIONS

    print(f"""
  STRATEGY: STRICT_PROD_V2 + Dynamic Exits (TREND: partial trail, EXP_NY: baseline)

  SLIPPAGE ROBUSTNESS:
    No slippage:   exp {base_m['exp']:+.3f}R  PF {base_m['pf']:.2f}  total {base_m['total_r']:+.0f}R
    +0.2R slip:    exp {slip02['exp']:+.3f}R  PF {slip02['pf']:.2f}  total {slip02['total_r']:+.0f}R  -> {'ROBUST' if slip02['exp'] > 0.25 else 'MARGINAL' if slip02['exp'] > 0.1 else 'FAIL'}
    +0.3R slip:    exp {slip03['exp']:+.3f}R  PF {slip03['pf']:.2f}  total {slip03['total_r']:+.0f}R  -> {'ROBUST' if slip03['exp'] > 0.25 else 'MARGINAL' if slip03['exp'] > 0.1 else 'FAIL'}
    Break-even:    {breakeven_slip:.3f}R per trade

  FTMO PASS PROBABILITY:
    Single (XAUUSD, 1% risk):        {single_pass:.1f}%
    Portfolio (5 instr, {best_risk}% risk):  {port_pass:.1f}%
    Portfolio + 0.2R slippage:        {port_slip_pass:.1f}%
    Avg days to pass (portfolio):     {port_avg_days:.0f} days
    Optimal risk per trade:           {best_risk}%

  VERDICT:
    Execution robust:  {'YES' if slip02['exp'] > 0.2 else 'MARGINAL' if slip02['exp'] > 0.1 else 'NO'}
    FTMO viable:       {'YES' if port_pass > 50 else 'MARGINAL' if port_pass > 25 else 'NO'}
""")

    # Save
    report_dir = Path("reports/latest")
    report_dir.mkdir(parents=True, exist_ok=True)
    path = report_dir / "robustness_ftmo.json"
    summary = {
        "base_metrics": base_m,
        "slippage_02": slip02,
        "slippage_03": slip03,
        "breakeven_slippage_r": breakeven_slip,
        "ftmo_single_pass_pct": single_pass,
        "ftmo_portfolio_pass_pct": port_pass,
        "ftmo_portfolio_slip_pass_pct": port_slip_pass,
        "ftmo_optimal_risk": best_risk,
        "ftmo_avg_days": port_avg_days,
    }
    with open(path, "w") as f:
        json.dump(summary, f, indent=2, default=str)
    print(f"  Results saved to {path}")
    print("=" * 70)


if __name__ == "__main__":
    main()
