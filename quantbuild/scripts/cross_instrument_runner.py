"""
Cross-Instrument Validation Runner.

Runs the exact same closed QuantBuild kernel on multiple instruments:
  1. Fetch 5yr data per instrument (Dukascopy)
  2. Run full kernel: regime + SQE + session filter + dynamic exits
  3. Generate per-instrument scorecard
  4. Apply promotion rubric: PROMOTE / WATCHLIST / REJECT
  5. Portfolio overlap analysis

Usage:
    python scripts/cross_instrument_runner.py
    python scripts/cross_instrument_runner.py --instruments XAUUSD EURUSD GBPUSD
    python scripts/cross_instrument_runner.py --skip-fetch
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
from src.quantbuild.io.parquet_loader import (
    load_parquet, save_parquet, _fetch_dukascopy,
)
from src.quantbuild.strategies.sqe_xauusd import (
    run_sqe_conditions, get_sqe_default_config, _compute_modules_once,
)
from src.quantbuild.strategy_modules.regime.detector import (
    RegimeDetector, REGIME_TREND, REGIME_EXPANSION, REGIME_COMPRESSION,
)

PERIOD_DAYS = 1825
CONFIG_PATH = "configs/strict_prod_v2.yaml"
PROFILES_PATH = "configs/instruments/instrument_profiles.yaml"
DEFAULT_INSTRUMENTS = ["XAUUSD", "XAGUSD", "EURUSD", "GBPUSD", "USDJPY"]


# ── Exit Functions (from production_analysis) ─────────────────────────

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
    """TREND: partial trail. EXPANSION_NY: baseline 2R."""
    if is_exp_ny:
        return exit_baseline(exc, tp_r=2.0, sl_r=1.0)
    # Partial trail: BE at 1R, trail 1.5R from peak
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


# ── Metrics ───────────────────────────────────────────────────────────

def compute_full_metrics(pnl_list, timestamps=None):
    if not pnl_list:
        return {
            "n": 0, "wr": 0, "pf": 0, "exp": 0, "total_r": 0,
            "max_dd": 0, "rdd": 0, "avg_win": 0, "avg_loss": 0,
            "median_mfe": 0, "median_mae": 0,
        }
    arr = np.array(pnl_list)
    wins = arr[arr > 0]
    losses = arr[arr < 0]
    gw = wins.sum() if len(wins) else 0
    gl = abs(losses.sum()) if len(losses) else 0
    pf = (gw / gl) if gl else (gw or 0)
    cum = np.cumsum(arr)
    peak = np.maximum.accumulate(cum)
    dd = peak - cum
    max_dd = float(-dd.max()) if len(dd) else 0
    rdd = float(cum[-1] / abs(max_dd)) if max_dd else 0

    # Yearly breakdown
    yearly = {}
    if timestamps:
        for ts, r in zip(timestamps, pnl_list):
            yr = ts.year if hasattr(ts, "year") else int(str(ts)[:4])
            yearly.setdefault(yr, []).append(r)

    return {
        "n": len(arr),
        "wr": float(100 * len(wins) / len(arr)),
        "pf": float(pf),
        "exp": float(arr.mean()),
        "total_r": float(arr.sum()),
        "max_dd": max_dd,
        "rdd": rdd,
        "avg_win": float(wins.mean()) if len(wins) else 0,
        "avg_loss": float(losses.mean()) if len(losses) else 0,
        "yearly": {yr: float(np.sum(rs)) for yr, rs in yearly.items()},
    }


# ── Data Fetching ─────────────────────────────────────────────────────

def fetch_instrument_data(symbol, base_path, days=PERIOD_DAYS):
    """Fetch 15m and 1h data for an instrument."""
    end = datetime.now()
    start = end - timedelta(days=days)

    for tf in ["15m", "1h"]:
        existing = load_parquet(base_path, symbol, tf, start=start, end=end)
        if len(existing) > 100:
            print(f"    {symbol} {tf}: {len(existing):,} bars (cached)")
            continue
        try:
            print(f"    Fetching {symbol} {tf} from Dukascopy ({days}d)...")
            data = _fetch_dukascopy(symbol, tf, start.replace(tzinfo=None), end.replace(tzinfo=None))
            if not data.empty:
                save_parquet(base_path, symbol, tf, data)
                print(f"    {symbol} {tf}: {len(data):,} bars saved")
            else:
                print(f"    WARNING: no data for {symbol} {tf}")
        except Exception as e:
            print(f"    ERROR fetching {symbol} {tf}: {e}")


# ── Core Kernel Run ───────────────────────────────────────────────────

def run_kernel_on_instrument(symbol, cfg, base_path, profiles):
    """Run the full closed kernel on one instrument. Returns results dict."""
    end = datetime.now()
    start = end - timedelta(days=PERIOD_DAYS)

    data = load_parquet(base_path, symbol, "15m", start=start, end=end)
    if data.empty or len(data) < 200:
        return {"symbol": symbol, "error": "insufficient_data", "bars": len(data)}
    data = data.sort_index()

    data_1h = load_parquet(base_path, symbol, "1h", start=start, end=end)
    if not data_1h.empty:
        data_1h = data_1h.sort_index()

    # Regime detection
    detector = RegimeDetector(config=cfg.get("regime", {}))
    regime_series = detector.classify(data, data_1h if not data_1h.empty else None)

    # SQE signals
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

    # Collect all signals with full context
    signals = []
    for i in range(1, len(data) - 1):
        for direction, mask in [("LONG", long_e), ("SHORT", short_e)]:
            if not mask.iloc[i]:
                continue
            ts = data.index[i]
            regime = regime_series.iloc[i] if i < len(regime_series) else REGIME_TREND
            session = session_from_timestamp(ts, mode=session_mode)
            rp = regime_profiles.get(regime, {})

            if rp.get("skip", False):
                continue
            allowed = rp.get("allowed_sessions")
            if allowed and session not in allowed:
                continue
            min_h = rp.get("min_hour_utc")
            if min_h is not None and ts.hour < min_h:
                continue

            exc = _full_excursion(sim_cache, i, direction)
            is_exp_ny = (
                regime == REGIME_EXPANSION
                and session in ("New York", "Overlap")
                and ts.hour >= 10
            )

            # MFE/MAE tracking
            mfe = max((f for f, a in exc), default=0) if exc else 0
            mae = max((a for f, a in exc), default=0) if exc else 0

            signals.append({
                "ts": ts, "direction": direction, "regime": regime,
                "session": session, "exc": exc, "is_exp_ny": is_exp_ny,
                "mfe": mfe, "mae": mae,
            })

    if not signals:
        return {"symbol": symbol, "error": "no_signals", "bars": len(data)}

    # Compute both exit strategies
    baseline_pnl = []
    dynamic_pnl = []
    timestamps = []
    mfe_winners = []
    mae_all = []
    regime_breakdown = {}

    for s in signals:
        bp = exit_baseline(s["exc"], tp_r=2.0, sl_r=1.0)
        dp = exit_dynamic(s["exc"], s["is_exp_ny"])
        baseline_pnl.append(bp)
        dynamic_pnl.append(dp)
        timestamps.append(s["ts"])
        mae_all.append(s["mae"])
        if bp > 0:
            mfe_winners.append(s["mfe"])

        r = s["regime"]
        regime_breakdown.setdefault(r, {"baseline": [], "dynamic": []})
        regime_breakdown[r]["baseline"].append(bp)
        regime_breakdown[r]["dynamic"].append(dp)

    baseline_m = compute_full_metrics(baseline_pnl, timestamps)
    dynamic_m = compute_full_metrics(dynamic_pnl, timestamps)

    # Slippage sensitivity
    slip_results = {}
    for slip in [0.0, 0.1, 0.2, 0.3]:
        adj = [p - slip for p in dynamic_pnl]
        slip_results[f"{slip:.1f}R"] = compute_full_metrics(adj)

    # Regime breakdown
    regime_metrics = {}
    for r, data_r in regime_breakdown.items():
        regime_metrics[r] = {
            "baseline": compute_full_metrics(data_r["baseline"]),
            "dynamic": compute_full_metrics(data_r["dynamic"]),
        }

    return {
        "symbol": symbol,
        "bars": len(data),
        "signals": len(signals),
        "baseline": baseline_m,
        "dynamic": dynamic_m,
        "slippage": slip_results,
        "regime_breakdown": regime_metrics,
        "median_mfe_winners": float(np.median(mfe_winners)) if mfe_winners else 0,
        "median_mae_all": float(np.median(mae_all)) if mae_all else 0,
        "dynamic_exit_improves": dynamic_m["total_r"] > baseline_m["total_r"],
        "timestamps": timestamps,
        "dynamic_pnl": dynamic_pnl,
    }


# ── Promotion Rubric ──────────────────────────────────────────────────

def apply_promotion_rubric(result, rubric):
    """Classify instrument as PROMOTE / WATCHLIST / REJECT."""
    if "error" in result:
        return "REJECT", f"Error: {result['error']}"

    dm = result["dynamic"]
    promo = rubric.get("promote", {})
    watch = rubric.get("watchlist", {})

    # Check PROMOTE
    reasons = []
    if dm["exp"] >= promo.get("min_expectancy_r", 0.15):
        reasons.append(f"exp {dm['exp']:.3f}R >= {promo['min_expectancy_r']}")
    else:
        reasons.append(f"exp {dm['exp']:.3f}R < {promo['min_expectancy_r']} FAIL")

    if dm["pf"] >= promo.get("min_profit_factor", 1.2):
        reasons.append(f"PF {dm['pf']:.2f} >= {promo['min_profit_factor']}")
    else:
        reasons.append(f"PF {dm['pf']:.2f} < {promo['min_profit_factor']} FAIL")

    if dm["max_dd"] >= promo.get("max_drawdown_r", -35):
        reasons.append(f"DD {dm['max_dd']:.0f}R >= {promo['max_drawdown_r']}")
    else:
        reasons.append(f"DD {dm['max_dd']:.0f}R < {promo['max_drawdown_r']} FAIL")

    if dm["n"] >= promo.get("min_trades", 50):
        reasons.append(f"trades {dm['n']} >= {promo['min_trades']}")
    else:
        reasons.append(f"trades {dm['n']} < {promo['min_trades']} FAIL")

    all_promote = all("FAIL" not in r for r in reasons)
    if all_promote:
        return "PROMOTE", "; ".join(reasons)

    # Check WATCHLIST
    w_reasons = []
    if dm["exp"] >= watch.get("min_expectancy_r", 0.05):
        w_reasons.append("exp OK")
    else:
        w_reasons.append("exp FAIL")
    if dm["pf"] >= watch.get("min_profit_factor", 1.0):
        w_reasons.append("PF OK")
    else:
        w_reasons.append("PF FAIL")
    if dm["n"] >= watch.get("min_trades", 30):
        w_reasons.append("trades OK")
    else:
        w_reasons.append("trades FAIL")

    all_watch = all("FAIL" not in r for r in w_reasons)
    if all_watch:
        return "WATCHLIST", "; ".join(reasons)

    return "REJECT", "; ".join(reasons)


# ── Portfolio Overlap Analysis ────────────────────────────────────────

def portfolio_overlap_report(all_results):
    """Analyze portfolio-level metrics for promoted instruments."""
    promoted = [r for r in all_results if r.get("promotion") == "PROMOTE"]
    if len(promoted) < 2:
        return {"error": "Need at least 2 promoted instruments"}

    # Build daily R series per instrument
    daily_series = {}
    for res in promoted:
        sym = res["symbol"]
        ts_list = res.get("timestamps", [])
        pnl_list = res.get("dynamic_pnl", [])
        if not ts_list:
            continue
        df = pd.DataFrame({"r": pnl_list}, index=pd.DatetimeIndex(ts_list))
        daily = df.resample("D").sum().fillna(0)
        daily_series[sym] = daily["r"]

    if len(daily_series) < 2:
        return {"error": "Insufficient daily data"}

    # Align all series
    combined = pd.DataFrame(daily_series).fillna(0)

    # Correlation matrix
    corr = combined.corr()

    # Portfolio equity curve
    portfolio_daily = combined.sum(axis=1)
    cum_portfolio = portfolio_daily.cumsum()
    peak = cum_portfolio.cummax()
    drawdown = cum_portfolio - peak

    # Same-day loss clustering
    loss_days = combined[combined < 0]
    n_instruments = len(daily_series)
    multi_loss_days = (loss_days < 0).sum(axis=1)
    cluster_3plus = int((multi_loss_days >= 3).sum())
    cluster_all = int((multi_loss_days >= n_instruments).sum())

    # Monthly returns
    monthly = portfolio_daily.resample("ME").sum()

    return {
        "instruments": list(daily_series.keys()),
        "correlation_matrix": corr.to_dict(),
        "avg_pairwise_correlation": float(
            corr.values[np.triu_indices_from(corr.values, k=1)].mean()
        ),
        "portfolio_total_r": float(cum_portfolio.iloc[-1]),
        "portfolio_max_dd": float(drawdown.min()),
        "portfolio_rdd": float(cum_portfolio.iloc[-1] / abs(drawdown.min())) if drawdown.min() < 0 else 0,
        "loss_cluster_3plus_days": cluster_3plus,
        "loss_cluster_all_days": cluster_all,
        "monthly_avg_r": float(monthly.mean()),
        "monthly_std_r": float(monthly.std()),
        "worst_month_r": float(monthly.min()),
        "best_month_r": float(monthly.max()),
        "pct_positive_months": float(100 * (monthly > 0).sum() / len(monthly)) if len(monthly) else 0,
    }


# ── Display ───────────────────────────────────────────────────────────

def print_scorecard(result):
    """Print detailed scorecard for one instrument."""
    sym = result["symbol"]
    if "error" in result:
        print(f"\n  {sym}: ERROR - {result['error']} ({result.get('bars', 0)} bars)")
        return

    dm = result["dynamic"]
    bm = result["baseline"]
    promo = result.get("promotion", "?")
    promo_reason = result.get("promotion_reason", "")

    print(f"\n  {'='*60}")
    print(f"  {sym} ({result.get('label', '')})")
    print(f"  {'='*60}")
    print(f"  Bars: {result['bars']:,} | Signals: {result['signals']}")
    print(f"  Promotion: [{promo}]")
    if promo_reason:
        print(f"  Reason: {promo_reason}")

    print(f"\n  {'Metric':>16s} {'Baseline':>10s} {'Dynamic':>10s} {'Delta':>10s}")
    print(f"  {'-'*50}")
    for key, label in [("n", "Trades"), ("wr", "Win Rate %"), ("pf", "PF"),
                        ("exp", "Expectancy"), ("total_r", "Total R"),
                        ("max_dd", "Max DD"), ("rdd", "R/DD")]:
        bv = bm.get(key, 0)
        dv = dm.get(key, 0)
        delta = dv - bv
        if key == "wr":
            print(f"  {label:>16s} {bv:>9.1f}% {dv:>9.1f}% {delta:>+9.1f}%")
        elif key in ("exp",):
            print(f"  {label:>16s} {bv:>+9.3f}R {dv:>+9.3f}R {delta:>+9.3f}R")
        elif key in ("total_r", "max_dd"):
            print(f"  {label:>16s} {bv:>+9.1f}R {dv:>+9.1f}R {delta:>+9.1f}R")
        elif key == "rdd":
            print(f"  {label:>16s} {bv:>9.2f} {dv:>9.2f} {delta:>+9.2f}")
        else:
            print(f"  {label:>16s} {bv:>9.0f} {dv:>9.0f} {delta:>+9.0f}")

    print(f"\n  Median MFE (winners): {result.get('median_mfe_winners', 0):.2f}R")
    print(f"  Median MAE (all):     {result.get('median_mae_all', 0):.2f}R")
    print(f"  Dynamic exit improves: {'YES' if result.get('dynamic_exit_improves') else 'NO'}")

    # Slippage
    print(f"\n  Slippage sensitivity:")
    for slip_key, sm in result.get("slippage", {}).items():
        status = "OK" if sm["exp"] > 0.15 else ("MARGINAL" if sm["exp"] > 0 else "FAIL")
        print(f"    {slip_key}: exp {sm['exp']:+.3f}R  PF {sm['pf']:.2f}  [{status}]")

    # Regime breakdown
    print(f"\n  Regime breakdown (dynamic exits):")
    for regime, rm in result.get("regime_breakdown", {}).items():
        rdm = rm["dynamic"]
        print(f"    {regime:>12s}: {rdm['n']:>3d} trades  WR {rdm['wr']:.0f}%  PF {rdm['pf']:.2f}  exp {rdm['exp']:+.3f}R  total {rdm['total_r']:+.1f}R")

    # Yearly
    print(f"\n  Yearly (dynamic):")
    for yr, yr_r in sorted(dm.get("yearly", {}).items()):
        print(f"    {yr}: {yr_r:+.1f}R")


# ── Main ──────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Cross-Instrument Validation")
    parser.add_argument("--instruments", nargs="+", default=None)
    parser.add_argument("--skip-fetch", action="store_true")
    parser.add_argument("--days", type=int, default=PERIOD_DAYS)
    args = parser.parse_args()

    print("=" * 70)
    print("  CROSS-INSTRUMENT VALIDATION RUNNER")
    print("=" * 70)

    cfg = load_config(CONFIG_PATH)
    setup_logging(cfg)

    with open(PROFILES_PATH) as f:
        profiles = yaml.safe_load(f)

    instruments_cfg = profiles.get("instruments", {})
    rubric = profiles.get("promotion", {})
    instrument_list = args.instruments or DEFAULT_INSTRUMENTS
    base_path = Path(cfg.get("data", {}).get("base_path", "data/market_cache"))

    # Step 1: Fetch data
    if not args.skip_fetch:
        print("\n  STEP 1: FETCHING DATA")
        print("-" * 70)
        for sym in instrument_list:
            print(f"\n  [{sym}]")
            fetch_instrument_data(sym, base_path, days=args.days)

    # Step 2: Run kernel on each instrument
    print("\n  STEP 2: RUNNING KERNEL")
    print("-" * 70)
    all_results = []

    for sym in instrument_list:
        print(f"\n  Running {sym}...")
        result = run_kernel_on_instrument(sym, cfg, base_path, profiles)
        inst_profile = instruments_cfg.get(sym, {})
        result["label"] = inst_profile.get("label", sym)
        result["asset_class"] = inst_profile.get("asset_class", "unknown")

        # Step 3: Apply promotion rubric
        promo, reason = apply_promotion_rubric(result, rubric)
        result["promotion"] = promo
        result["promotion_reason"] = reason

        all_results.append(result)

    # Step 4: Print scorecards
    print("\n" + "=" * 70)
    print("  STEP 3: INSTRUMENT SCORECARDS")
    print("=" * 70)

    for result in all_results:
        print_scorecard(result)

    # Summary table
    print("\n" + "=" * 70)
    print("  PROMOTION SUMMARY")
    print("=" * 70)

    print(f"\n  {'Symbol':>8s} {'Class':>10s} {'Trades':>7s} {'WR':>6s} {'PF':>6s} "
          f"{'Exp':>7s} {'TotalR':>8s} {'MaxDD':>7s} {'R/DD':>6s} {'Verdict':>10s}")
    print("  " + "-" * 80)

    for r in all_results:
        if "error" in r:
            print(f"  {r['symbol']:>8s} {'?':>10s} {'--':>7s} {'--':>6s} {'--':>6s} "
                  f"{'--':>7s} {'--':>8s} {'--':>7s} {'--':>6s} {r['promotion']:>10s}")
            continue
        dm = r["dynamic"]
        print(f"  {r['symbol']:>8s} {r.get('asset_class','?'):>10s} {dm['n']:>7d} "
              f"{dm['wr']:>5.1f}% {dm['pf']:>6.2f} {dm['exp']:>+6.3f}R "
              f"{dm['total_r']:>+7.1f}R {dm['max_dd']:>+6.1f}R {dm['rdd']:>5.2f} "
              f"{r['promotion']:>10s}")

    promoted = [r for r in all_results if r.get("promotion") == "PROMOTE"]
    watchlist = [r for r in all_results if r.get("promotion") == "WATCHLIST"]
    rejected = [r for r in all_results if r.get("promotion") == "REJECT"]

    print(f"\n  PROMOTE:   {', '.join(r['symbol'] for r in promoted) or 'none'}")
    print(f"  WATCHLIST: {', '.join(r['symbol'] for r in watchlist) or 'none'}")
    print(f"  REJECT:    {', '.join(r['symbol'] for r in rejected) or 'none'}")

    # Step 5: Portfolio overlap (if 2+ promoted)
    if len(promoted) >= 2:
        print("\n" + "=" * 70)
        print("  STEP 4: PORTFOLIO OVERLAP ANALYSIS")
        print("=" * 70)

        overlap = portfolio_overlap_report(promoted)
        if "error" not in overlap:
            print(f"\n  Instruments: {', '.join(overlap['instruments'])}")
            print(f"  Avg pairwise correlation: {overlap['avg_pairwise_correlation']:.3f}")
            print(f"\n  Portfolio total R:  {overlap['portfolio_total_r']:+.1f}R")
            print(f"  Portfolio max DD:   {overlap['portfolio_max_dd']:+.1f}R")
            print(f"  Portfolio R/DD:     {overlap['portfolio_rdd']:.2f}")
            print(f"\n  Monthly avg:        {overlap['monthly_avg_r']:+.2f}R")
            print(f"  Monthly std:        {overlap['monthly_std_r']:.2f}R")
            print(f"  Worst month:        {overlap['worst_month_r']:+.2f}R")
            print(f"  Best month:         {overlap['best_month_r']:+.2f}R")
            print(f"  % positive months:  {overlap['pct_positive_months']:.0f}%")
            print(f"\n  Loss clustering:")
            print(f"    3+ instruments losing same day: {overlap['loss_cluster_3plus_days']} days")
            print(f"    ALL instruments losing same day: {overlap['loss_cluster_all_days']} days")

            # Correlation matrix
            print(f"\n  Correlation matrix:")
            syms = overlap["instruments"]
            print(f"  {'':>8s} " + " ".join(f"{s:>8s}" for s in syms))
            for s1 in syms:
                vals = " ".join(
                    f"{overlap['correlation_matrix'].get(s1, {}).get(s2, 0):>8.3f}"
                    for s2 in syms
                )
                print(f"  {s1:>8s} {vals}")

            # FTMO projection
            total_trades_yr = sum(
                r["dynamic"]["n"] / (PERIOD_DAYS / 365.25) for r in promoted
            )
            avg_exp = np.mean([r["dynamic"]["exp"] for r in promoted])
            print(f"\n  FTMO PROJECTION (portfolio):")
            print(f"    Trades/year: {total_trades_yr:.0f}")
            print(f"    Avg expectancy: {avg_exp:.3f}R")
            print(f"    At 1% risk: {total_trades_yr * avg_exp * 1:.1f}% annual")
            print(f"    At 1.5% risk: {total_trades_yr * avg_exp * 1.5:.1f}% annual")
            monthly_r = total_trades_yr * avg_exp / 12
            print(f"    Monthly R: {monthly_r:.1f}R")
            print(f"    At 1% risk: {monthly_r * 1:.1f}% per month")
        else:
            print(f"\n  {overlap['error']}")

    # Save results
    report_dir = Path("reports/latest")
    report_dir.mkdir(parents=True, exist_ok=True)

    save_data = []
    for r in all_results:
        rd = {k: v for k, v in r.items() if k not in ("timestamps", "dynamic_pnl", "exc")}
        save_data.append(rd)

    report_path = report_dir / "cross_instrument_validation.json"
    with open(report_path, "w") as f:
        json.dump(save_data, f, indent=2, default=str)
    print(f"\n  Results saved to {report_path}")
    print("=" * 70)


if __name__ == "__main__":
    main()
