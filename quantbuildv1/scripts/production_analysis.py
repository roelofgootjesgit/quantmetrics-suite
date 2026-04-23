"""
Production Analysis: V2 + Dynamic Exits + Monte Carlo + Portfolio Projection.

Combines everything into the definitive analysis:
  1. V2 with segment-specific exits (TREND: partial trail, EXPANSION_NY: runner)
  2. Monte Carlo: 500 random shuffles for DD distribution and worst-case equity
  3. Combined segment analysis with yearly breakdown
  4. Portfolio scaling projection: 5 instruments

Usage:
    python scripts/production_analysis.py
"""
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd

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
MC_ITERATIONS = 500


# ── Exit simulation functions ──────────────────────────────────────────

def _full_excursion(cache, i, direction, atr, max_bars=200):
    close_arr, high_arr, low_arr, ts_arr = cache["close"], cache["high"], cache["low"], cache["ts"]
    n = len(close_arr)
    entry_price = float(close_arr[i])
    risk = atr if atr > 0 else entry_price * 0.005
    bars = []
    for j in range(i + 1, min(i + max_bars, n)):
        if direction == "LONG":
            fav = (high_arr[j] - entry_price) / risk
            adv = (entry_price - low_arr[j]) / risk
        else:
            fav = (entry_price - low_arr[j]) / risk
            adv = (high_arr[j] - entry_price) / risk
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
    """50% off at partial_at, rest trails with trail_r distance from peak."""
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
        trail_exit = max(0, peak - trail_r)
        return partial_at * 0.5 + trail_exit * 0.5
    return 0.0


def exit_runner(exc, sl_r=1.0, trail_start=1.5, trail_dist=1.0):
    """Pure runner: no fixed cap, trail kicks in after trail_start R."""
    peak = 0.0
    trailing = False
    for fav, adv in exc:
        if adv >= sl_r:
            return -sl_r
        peak = max(peak, fav)
        if not trailing and peak >= trail_start:
            trailing = True
        if trailing:
            if peak - fav >= trail_dist:
                return max(0, peak - trail_dist)
    if trailing:
        return max(0, peak - trail_dist)
    return 0.0


# ── Metrics ────────────────────────────────────────────────────────────

def compute_metrics(pnl_list):
    if not pnl_list:
        return {"n": 0, "total_r": 0, "wr": 0, "exp": 0, "pf": 0, "max_dd": 0, "avg_r": 0}
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
        "avg_win": float(wins.mean()) if len(wins) else 0,
        "avg_loss": float(losses.mean()) if len(losses) else 0,
        "avg_r": float(arr.mean()),
    }


def equity_curve(pnl_list):
    return np.cumsum(pnl_list)


# ── Monte Carlo ───────────────────────────────────────────────────────

def monte_carlo(pnl_list, iterations=500):
    arr = np.array(pnl_list)
    n = len(arr)
    max_dds = []
    final_rs = []
    worst_equity = np.full(n, np.inf)

    for _ in range(iterations):
        shuffled = np.random.permutation(arr)
        cum = np.cumsum(shuffled)
        peak = np.maximum.accumulate(cum)
        dd = peak - cum
        max_dds.append(dd.max())
        final_rs.append(cum[-1])
        worst_equity = np.minimum(worst_equity, cum)

    return {
        "max_dd_median": float(np.median(max_dds)),
        "max_dd_95pct": float(np.percentile(max_dds, 95)),
        "max_dd_99pct": float(np.percentile(max_dds, 99)),
        "max_dd_worst": float(np.max(max_dds)),
        "final_r_median": float(np.median(final_rs)),
        "final_r_5pct": float(np.percentile(final_rs, 5)),
        "final_r_95pct": float(np.percentile(final_rs, 95)),
        "worst_equity_curve": worst_equity.tolist(),
        "iterations": iterations,
    }


# ── Main ──────────────────────────────────────────────────────────────

def main():
    print("=" * 70)
    print("  PRODUCTION ANALYSIS: V2 + Dynamic Exits + Monte Carlo")
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

    print(f"\n  Data: {len(data):,} bars, {data.index[0]} -> {data.index[-1]}")

    # Regime
    detector = RegimeDetector(config=cfg.get("regime", {}))
    regime_series = detector.classify(data, data_1h if not data_1h.empty else None)

    # Entry signals
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
    atr_arr = sim_cache["atr"]
    regime_profiles = cfg.get("regime_profiles", {})

    # Build filtered signal list (V2 rules)
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
            atr = float(atr_arr[i])
            exc = _full_excursion(sim_cache, i, direction, atr)
            is_exp_ny = (regime == REGIME_EXPANSION and session in ("New York", "Overlap") and ts.hour >= 10)
            signals.append({
                "i": i, "direction": direction, "ts": ts,
                "regime": regime, "session": session, "atr": atr,
                "year": ts.year, "exc": exc, "is_exp_ny": is_exp_ny,
            })

    print(f"  V2-filtered signals: {len(signals)}")
    trend_sigs = [s for s in signals if s["regime"] == REGIME_TREND]
    exp_ny_sigs = [s for s in signals if s["is_exp_ny"]]
    other_exp = [s for s in signals if s["regime"] == REGIME_EXPANSION and not s["is_exp_ny"]]
    print(f"    TREND: {len(trend_sigs)} | EXPANSION_NY: {len(exp_ny_sigs)} | other: {len(other_exp)}")

    # =========================================================
    # SECTION 1: SEGMENT-SPECIFIC EXIT BACKTEST
    # =========================================================
    print("\n" + "=" * 70)
    print("  SECTION 1: SEGMENT-SPECIFIC EXITS (5 year backtest)")
    print("=" * 70)

    # Strategy: TREND gets partial trail (C), EXPANSION_NY gets runner (D)
    # Other expansion signals also get runner
    combined_pnl = []
    baseline_pnl = []
    trade_log = []

    for s in signals:
        exc = s["exc"]
        bl = exit_baseline(exc)
        baseline_pnl.append(bl)

        if s["is_exp_ny"]:
            pnl = exit_runner(exc, sl_r=1.0, trail_start=2.0, trail_dist=1.0)
            exit_type = "D_runner"
        elif s["regime"] == REGIME_EXPANSION:
            pnl = exit_runner(exc, sl_r=1.0, trail_start=1.5, trail_dist=1.0)
            exit_type = "D_runner"
        else:
            pnl = exit_partial_trail(exc, sl_r=1.0, partial_at=1.0, trail_r=1.5)
            exit_type = "C_trail"

        combined_pnl.append(pnl)
        trade_log.append({
            "ts": s["ts"], "year": s["year"], "regime": s["regime"],
            "session": s["session"], "direction": s["direction"],
            "exit_type": exit_type, "pnl_baseline": bl, "pnl_combined": pnl,
            "is_exp_ny": s["is_exp_ny"],
        })

    bm = compute_metrics(baseline_pnl)
    cm = compute_metrics(combined_pnl)

    def _print_comparison(label_a, ma, label_b, mb):
        header = f"  {'Metric':<20s} {label_a:>14s} {label_b:>14s} {'Delta':>12s}"
        print(header)
        print("  " + "-" * (len(header) - 2))
        for name, a, b, fmt in [
            ("Trades", ma["n"], mb["n"], "d"),
            ("Win Rate", ma["wr"], mb["wr"], ".1f"),
            ("PF", ma["pf"], mb["pf"], ".2f"),
            ("Expectancy", ma["exp"], mb["exp"], ".3f"),
            ("Total R", ma["total_r"], mb["total_r"], ".1f"),
            ("Max DD", ma["max_dd"], mb["max_dd"], ".1f"),
            ("R/DD", ma["total_r"]/abs(ma["max_dd"]) if ma["max_dd"] else 0,
             mb["total_r"]/abs(mb["max_dd"]) if mb["max_dd"] else 0, ".2f"),
            ("Avg Win", ma.get("avg_win", 0), mb.get("avg_win", 0), ".2f"),
            ("Avg Loss", ma.get("avg_loss", 0), mb.get("avg_loss", 0), ".2f"),
        ]:
            delta = b - a
            sign = "+" if delta >= 0 else ""
            print(f"  {name:<20s} {format(a, fmt):>14s} {format(b, fmt):>14s} "
                  f"{sign}{format(delta, fmt):>11s}")

    _print_comparison("BASELINE_2R", bm, "COMBINED_DYN", cm)

    # =========================================================
    # SECTION 2: YEARLY BREAKDOWN
    # =========================================================
    print("\n" + "=" * 70)
    print("  SECTION 2: YEARLY BREAKDOWN")
    print("=" * 70)

    years = sorted(set(t["year"] for t in trade_log))
    print(f"\n  {'Year':<6s} {'N':>4s} {'BL_R':>8s} {'DYN_R':>8s} {'Delta':>8s} "
          f"{'BL_WR':>7s} {'DYN_WR':>7s} {'DYN_PF':>7s}")
    print("  " + "-" * 60)

    for year in years:
        yr = [t for t in trade_log if t["year"] == year]
        bl_yr = [t["pnl_baseline"] for t in yr]
        dy_yr = [t["pnl_combined"] for t in yr]
        bl_m = compute_metrics(bl_yr)
        dy_m = compute_metrics(dy_yr)
        delta = dy_m["total_r"] - bl_m["total_r"]
        print(f"  {year:<6d} {len(yr):>4d} {bl_m['total_r']:>+7.1f}R {dy_m['total_r']:>+7.1f}R "
              f"{delta:>+7.1f}R {bl_m['wr']:>6.1f}% {dy_m['wr']:>6.1f}% {dy_m['pf']:>6.2f}")

    # =========================================================
    # SECTION 3: SEGMENT BREAKDOWN
    # =========================================================
    print("\n" + "=" * 70)
    print("  SECTION 3: SEGMENT BREAKDOWN")
    print("=" * 70)

    for label, filt in [
        ("TREND (exit C: partial trail)", lambda t: t["regime"] == REGIME_TREND),
        ("EXPANSION_NY (exit D: runner 2.0)", lambda t: t["is_exp_ny"]),
        ("EXPANSION other (exit D: runner 1.5)", lambda t: t["regime"] == REGIME_EXPANSION and not t["is_exp_ny"]),
    ]:
        seg = [t for t in trade_log if filt(t)]
        if not seg:
            continue
        bl_pnl = [t["pnl_baseline"] for t in seg]
        dy_pnl = [t["pnl_combined"] for t in seg]
        blm = compute_metrics(bl_pnl)
        dym = compute_metrics(dy_pnl)
        print(f"\n  {label} ({len(seg)} trades)")
        _print_comparison("BASELINE", blm, "DYNAMIC", dym)

    # =========================================================
    # SECTION 4: MONTE CARLO SIMULATION
    # =========================================================
    print("\n" + "=" * 70)
    print(f"  SECTION 4: MONTE CARLO ({MC_ITERATIONS} iterations)")
    print("=" * 70)

    np.random.seed(42)

    for label, pnl in [("BASELINE_2R", baseline_pnl), ("COMBINED_DYN", combined_pnl)]:
        mc = monte_carlo(pnl, MC_ITERATIONS)
        print(f"\n  {label} ({len(pnl)} trades)")
        print(f"    Final R (median):     {mc['final_r_median']:>+8.1f}R")
        print(f"    Final R (5th pct):    {mc['final_r_5pct']:>+8.1f}R")
        print(f"    Final R (95th pct):   {mc['final_r_95pct']:>+8.1f}R")
        print(f"    Max DD (median):      {mc['max_dd_median']:>8.1f}R")
        print(f"    Max DD (95th pct):    {mc['max_dd_95pct']:>8.1f}R")
        print(f"    Max DD (99th pct):    {mc['max_dd_99pct']:>8.1f}R")
        print(f"    Max DD (worst):       {mc['max_dd_worst']:>8.1f}R")

        if label == "COMBINED_DYN":
            mc_combined = mc

    # =========================================================
    # SECTION 5: PORTFOLIO SCALING PROJECTION
    # =========================================================
    print("\n" + "=" * 70)
    print("  SECTION 5: PORTFOLIO SCALING PROJECTION")
    print("=" * 70)

    instruments = ["XAUUSD", "XAGUSD", "EURUSD", "GBPUSD", "NAS100"]
    xau_exp = cm["exp"]
    xau_trades_yr = cm["n"] / (PERIOD_DAYS / 365.25)
    xau_dd = abs(cm["max_dd"])

    # Conservative assumptions: other instruments have 60-80% of XAUUSD edge
    instrument_factors = {
        "XAUUSD": 1.0,
        "XAGUSD": 0.85,
        "EURUSD": 0.65,
        "GBPUSD": 0.70,
        "NAS100": 0.75,
    }

    print(f"\n  Base edge (XAUUSD): {xau_exp:.3f}R/trade, {xau_trades_yr:.0f} trades/yr")
    print(f"\n  {'Instrument':<12s} {'Factor':>7s} {'Exp/trade':>10s} {'Trades/yr':>10s} {'R/yr':>8s}")
    print("  " + "-" * 52)

    total_r_yr = 0
    total_trades_yr = 0
    for inst in instruments:
        factor = instrument_factors[inst]
        inst_exp = xau_exp * factor
        inst_trades = xau_trades_yr * (0.9 if inst != "XAUUSD" else 1.0)
        inst_r_yr = inst_exp * inst_trades
        total_r_yr += inst_r_yr
        total_trades_yr += inst_trades
        print(f"  {inst:<12s} {factor:>6.0%} {inst_exp:>+9.3f}R {inst_trades:>9.0f} {inst_r_yr:>+7.1f}R")

    print("  " + "-" * 52)
    print(f"  {'TOTAL':<12s} {'':>7s} {'':>10s} {total_trades_yr:>9.0f} {total_r_yr:>+7.1f}R")

    risk_pcts = [0.5, 0.75, 1.0, 1.5]
    print(f"\n  PROJECTED ANNUAL RETURNS:")
    print(f"  {'Risk/trade':>12s} {'R/year':>8s} {'Annual%':>8s} {'Monthly%':>9s} {'FTMO 10% in':>14s}")
    print("  " + "-" * 56)

    for risk_pct in risk_pcts:
        annual_pct = total_r_yr * risk_pct
        monthly_pct = annual_pct / 12
        r_per_month = total_r_yr / 12
        months_to_10r = 10 / r_per_month if r_per_month > 0 else float("inf")
        print(f"  {risk_pct:>11.1f}% {total_r_yr:>+7.1f}R {annual_pct:>+7.1f}% "
              f"{monthly_pct:>+8.2f}% {months_to_10r:>10.1f} mo")

    # Monte Carlo DD for portfolio (conservative: sqrt(5) * single instrument DD)
    port_dd_95 = mc_combined["max_dd_95pct"] * 1.2  # 20% buffer for correlation
    port_dd_99 = mc_combined["max_dd_99pct"] * 1.2

    print(f"\n  RISK ASSESSMENT (portfolio):")
    print(f"    Expected max DD (95th pct):  {port_dd_95:.1f}R")
    print(f"    Expected max DD (99th pct):  {port_dd_99:.1f}R")
    print(f"    At 1% risk:                  {port_dd_95 * 1:.1f}% account drawdown (95th)")
    print(f"    At 0.5% risk:                {port_dd_95 * 0.5:.1f}% account drawdown (95th)")

    # =========================================================
    # SECTION 6: EXECUTIVE SUMMARY
    # =========================================================
    print("\n" + "=" * 70)
    print("  EXECUTIVE SUMMARY")
    print("=" * 70)

    print(f"""
  STRATEGY: STRICT_PROD_V2 + Dynamic Exits
  PERIOD:   5 years XAUUSD (2021-2026)

  SINGLE INSTRUMENT (XAUUSD):
    Trades/year:         {xau_trades_yr:.0f}
    Expectancy:          {cm['exp']:.3f}R/trade
    PF:                  {cm['pf']:.2f}
    Total R (5yr):       {cm['total_r']:+.1f}R
    R/year:              {cm['total_r']/(PERIOD_DAYS/365.25):+.1f}R
    Max DD:              {cm['max_dd']:.1f}R
    R/DD ratio:          {cm['total_r']/abs(cm['max_dd']):.2f}
    MC worst DD (99th):  {mc_combined['max_dd_99pct']:.1f}R

  PORTFOLIO (5 instruments, conservative):
    Trades/year:         {total_trades_yr:.0f}
    R/year:              {total_r_yr:+.1f}R
    At 1% risk:          {total_r_yr * 1:+.1f}% annual return
    Monthly return:      {total_r_yr * 1 / 12:+.2f}%
    FTMO 10% target:     {10 / (total_r_yr / 12):.1f} months

  VERDICT:
    3-6% monthly target: {"ACHIEVABLE" if total_r_yr * 1 / 12 >= 3 else "NEEDS MORE SCALE" if total_r_yr * 1 / 12 >= 2 else "NOT YET"}
    at {"1.0" if total_r_yr * 1 / 12 >= 3 else "1.5"}% risk per trade with {len(instruments)} instruments
""")

    # Save
    report_dir = Path("reports/latest")
    report_dir.mkdir(parents=True, exist_ok=True)
    summary = {
        "strategy": "STRICT_PROD_V2 + Dynamic Exits",
        "period_days": PERIOD_DAYS,
        "baseline": bm, "combined": cm,
        "monte_carlo_baseline": monte_carlo(baseline_pnl, MC_ITERATIONS),
        "monte_carlo_combined": mc_combined,
        "portfolio_r_year": total_r_yr,
        "portfolio_trades_year": total_trades_yr,
    }
    path = report_dir / "production_analysis.json"
    with open(path, "w") as f:
        json.dump(summary, f, indent=2, default=str)
    print(f"  Results saved to {path}")
    print("=" * 70)


if __name__ == "__main__":
    main()
