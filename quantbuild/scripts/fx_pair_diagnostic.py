"""
FX Pair Diagnostic — Deep analysis for USDCHF, AUDUSD, USDCAD, NZDUSD.

For each pair, determines:
  1. Does the SQE trend kernel work? (baseline + dynamic exits)
  2. Per-regime breakdown (TREND / EXPANSION / COMPRESSION)
  3. Per-session breakdown (London / NY / Overlap / Asia)
  4. MFE/MAE analysis — entries good but exits bad? -> MR candidate
  5. Mean reversion backtest on COMPRESSION regime
  6. Direction bias (LONG vs SHORT)
  7. Yearly stability
  8. Role recommendation: CORE_TREND / THROUGHPUT / MEAN_REVERSION / REGIME_FILTER / REJECT

Usage:
    python scripts/fx_pair_diagnostic.py
    python scripts/fx_pair_diagnostic.py --instruments USDCHF AUDUSD
"""
import argparse
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
from src.quantbuild.indicators.atr import atr as compute_atr
from src.quantbuild.io.parquet_loader import (
    load_parquet, save_parquet, _fetch_dukascopy,
)
from src.quantbuild.strategies.sqe_xauusd import (
    run_sqe_conditions, get_sqe_default_config, _compute_modules_once,
)
from src.quantbuild.strategies.mean_reversion_eurusd import (
    run_mr_conditions, simulate_mr_trade, DEFAULT_MR_CONFIG,
)
from src.quantbuild.strategy_modules.regime.detector import (
    RegimeDetector, REGIME_TREND, REGIME_EXPANSION, REGIME_COMPRESSION,
)

CONFIG_PATH = "configs/strict_prod_v2.yaml"
PERIOD_DAYS = 1825
TARGET_PAIRS = ["USDCHF", "AUDUSD", "USDCAD", "NZDUSD"]


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


# ── Metrics ───────────────────────────────────────────────────────────

def metrics(pnl_list, timestamps=None):
    if not pnl_list:
        return {"n": 0, "wr": 0, "pf": 0, "exp": 0, "total_r": 0,
                "max_dd": 0, "rdd": 0, "avg_win": 0, "avg_loss": 0}
    arr = np.array(pnl_list)
    wins = arr[arr > 0]
    losses = arr[arr < 0]
    gw = wins.sum() if len(wins) else 0
    gl = abs(losses.sum()) if len(losses) else 0.001
    cum = np.cumsum(arr)
    peak = np.maximum.accumulate(cum)
    dd = peak - cum
    max_dd = float(-dd.max()) if len(dd) else 0
    rdd = float(cum[-1] / abs(max_dd)) if max_dd else 0

    yearly = {}
    if timestamps:
        for ts, r in zip(timestamps, pnl_list):
            yr = ts.year if hasattr(ts, "year") else int(str(ts)[:4])
            yearly.setdefault(yr, []).append(r)

    return {
        "n": len(arr),
        "wr": float(100 * len(wins) / len(arr)),
        "pf": float(gw / gl),
        "exp": float(arr.mean()),
        "total_r": float(arr.sum()),
        "max_dd": max_dd,
        "rdd": rdd,
        "avg_win": float(wins.mean()) if len(wins) else 0,
        "avg_loss": float(losses.mean()) if len(losses) else 0,
        "yearly": {yr: float(np.sum(rs)) for yr, rs in yearly.items()},
    }


# ── Data Fetch ────────────────────────────────────────────────────────

def ensure_data(symbol, base_path, days=PERIOD_DAYS):
    end = datetime.now()
    start = end - timedelta(days=days)
    for tf in ["15m", "1h"]:
        existing = load_parquet(base_path, symbol, tf, start=start, end=end)
        if len(existing) > 1000:
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


# ── Full Diagnostic ───────────────────────────────────────────────────

def diagnose_pair(symbol, cfg, base_path):
    """Run comprehensive diagnostic on a single FX pair."""
    end = datetime.now()
    start = end - timedelta(days=PERIOD_DAYS)

    data_15m = load_parquet(base_path, symbol, "15m", start=start, end=end)
    if data_15m.empty or len(data_15m) < 500:
        return {"symbol": symbol, "error": "insufficient_data", "bars": len(data_15m)}
    data_15m = data_15m.sort_index()

    data_1h = load_parquet(base_path, symbol, "1h", start=start, end=end)
    if not data_1h.empty:
        data_1h = data_1h.sort_index()

    # ── Regime Detection ──
    detector = RegimeDetector(config=cfg.get("regime", {}))
    regime_series = detector.classify(data_15m, data_1h if not data_1h.empty else None)

    regime_dist = {}
    for reg in [REGIME_TREND, REGIME_EXPANSION, REGIME_COMPRESSION]:
        count = int((regime_series == reg).sum())
        regime_dist[reg] = round(100 * count / len(regime_series), 1)

    # ── SQE Trend Signals ──
    sqe_cfg = get_sqe_default_config()
    strategy_cfg = cfg.get("strategy", {}) or {}
    if strategy_cfg:
        _deep_merge(sqe_cfg, strategy_cfg)

    precomputed_df = _compute_modules_once(data_15m, sqe_cfg)
    long_e = run_sqe_conditions(data_15m, "LONG", sqe_cfg, _precomputed_df=precomputed_df)
    short_e = run_sqe_conditions(data_15m, "SHORT", sqe_cfg, _precomputed_df=precomputed_df)

    if strategy_cfg.get("structure_use_h1_gate", False) and not data_1h.empty:
        long_e = _apply_h1_gate(long_e, data_15m, "LONG", base_path, symbol, start, end, sqe_cfg)
        short_e = _apply_h1_gate(short_e, data_15m, "SHORT", base_path, symbol, start, end, sqe_cfg)

    sim_cache = _prepare_sim_cache(data_15m)

    # ── Collect all SQE signals (no regime filter — we analyze ALL) ──
    signals = []
    for i in range(1, len(data_15m) - 1):
        for direction, mask in [("LONG", long_e), ("SHORT", short_e)]:
            if not mask.iloc[i]:
                continue
            ts = data_15m.index[i]
            regime = regime_series.iloc[i] if i < len(regime_series) else REGIME_TREND
            session = session_from_timestamp(ts, mode="extended")

            exc = _full_excursion(sim_cache, i, direction)
            is_exp_ny = (
                regime == REGIME_EXPANSION
                and session in ("New York", "Overlap")
                and ts.hour >= 10
            )

            bp = exit_baseline(exc, tp_r=2.0, sl_r=1.0)
            dp = exit_dynamic(exc, is_exp_ny)
            mfe = max((f for f, _ in exc), default=0) if exc else 0
            mae = max((a for _, a in exc), default=0) if exc else 0

            signals.append({
                "ts": ts, "direction": direction, "regime": regime,
                "session": session, "pnl_base": bp, "pnl_dyn": dp,
                "mfe": mfe, "mae": mae, "year": ts.year,
            })

    # ── Mean Reversion Test (COMPRESSION only) ──
    mr_signals = []
    for mr_dir in ["LONG", "SHORT"]:
        mr_entries = run_mr_conditions(
            data_15m, mr_dir, config=DEFAULT_MR_CONFIG, regime_series=regime_series
        )
        for i in range(len(data_15m)):
            if not mr_entries.iloc[i]:
                continue
            result = simulate_mr_trade(
                sim_cache, i, mr_dir,
                tp_r=DEFAULT_MR_CONFIG["tp_r"],
                sl_r=DEFAULT_MR_CONFIG["sl_r"],
                time_stop_bars=DEFAULT_MR_CONFIG["time_stop_bars"],
            )
            ts = data_15m.index[i]
            mr_signals.append({
                "ts": ts, "direction": mr_dir,
                "pnl_r": result["pnl_r"], "mfe": result["mfe"],
                "mae": result["mae"], "exit_type": result["exit_type"],
                "bars_held": result["bars_held"], "year": ts.year,
            })

    return _build_report(symbol, data_15m, signals, mr_signals, regime_dist)


def _build_report(symbol, data, signals, mr_signals, regime_dist):
    """Compile all analyses into a structured report."""
    report = {
        "symbol": symbol,
        "bars": len(data),
        "period": f"{data.index[0].date()} to {data.index[-1].date()}",
        "regime_distribution": regime_dist,
    }

    if not signals:
        report["trend_analysis"] = {"error": "no_signals"}
        report["role_recommendation"] = "REGIME_FILTER"
        report["role_reason"] = "No SQE trend signals generated"
        return report

    # ── Overall Trend Analysis ──
    base_pnl = [s["pnl_base"] for s in signals]
    dyn_pnl = [s["pnl_dyn"] for s in signals]
    ts_list = [s["ts"] for s in signals]

    report["trend_analysis"] = {
        "baseline": metrics(base_pnl, ts_list),
        "dynamic": metrics(dyn_pnl, ts_list),
        "dynamic_improves": sum(dyn_pnl) > sum(base_pnl),
    }

    # ── Per-Regime Breakdown ──
    regime_results = {}
    for reg in [REGIME_TREND, REGIME_EXPANSION, REGIME_COMPRESSION]:
        r_sigs = [s for s in signals if s["regime"] == reg]
        if not r_sigs:
            regime_results[reg] = {"n": 0}
            continue
        r_base = [s["pnl_base"] for s in r_sigs]
        r_dyn = [s["pnl_dyn"] for s in r_sigs]
        r_ts = [s["ts"] for s in r_sigs]
        r_mfe = [s["mfe"] for s in r_sigs]
        r_mae = [s["mae"] for s in r_sigs]
        regime_results[reg] = {
            "baseline": metrics(r_base, r_ts),
            "dynamic": metrics(r_dyn, r_ts),
            "median_mfe": float(np.median(r_mfe)),
            "median_mae": float(np.median(r_mae)),
        }
    report["regime_breakdown"] = regime_results

    # ── Per-Session Breakdown ──
    session_results = {}
    for sess in set(s["session"] for s in signals):
        s_sigs = [s for s in signals if s["session"] == sess]
        s_dyn = [s["pnl_dyn"] for s in s_sigs]
        session_results[sess] = metrics(s_dyn)
    report["session_breakdown"] = session_results

    # ── Direction Analysis ──
    dir_results = {}
    for d in ["LONG", "SHORT"]:
        d_sigs = [s for s in signals if s["direction"] == d]
        if d_sigs:
            d_dyn = [s["pnl_dyn"] for s in d_sigs]
            dir_results[d] = metrics(d_dyn)
    report["direction_breakdown"] = dir_results

    # ── MFE/MAE Deep Dive ──
    all_mfe = np.array([s["mfe"] for s in signals])
    all_mae = np.array([s["mae"] for s in signals])
    loser_mfe = np.array([s["mfe"] for s in signals if s["pnl_base"] < 0])

    mfe_mae = {
        "mfe_mean": round(float(all_mfe.mean()), 2),
        "mfe_median": round(float(np.median(all_mfe)), 2),
        "mfe_p25": round(float(np.percentile(all_mfe, 25)), 2),
        "mfe_p75": round(float(np.percentile(all_mfe, 75)), 2),
        "mae_mean": round(float(all_mae.mean()), 2),
        "mae_median": round(float(np.median(all_mae)), 2),
    }
    if len(loser_mfe):
        mfe_mae["loser_mfe_median"] = round(float(np.median(loser_mfe)), 2)
        mfe_mae["losers_with_mfe_above_1r"] = round(float(100 * (loser_mfe > 1.0).mean()), 1)
        mfe_mae["mean_reversion_signal"] = bool(np.median(loser_mfe) > 1.0)
    else:
        mfe_mae["mean_reversion_signal"] = False
    report["mfe_mae_analysis"] = mfe_mae

    # ── Slippage Sensitivity ──
    slip_results = {}
    for slip in [0.0, 0.1, 0.2, 0.3]:
        adj = [p - slip for p in dyn_pnl]
        m = metrics(adj)
        slip_results[f"{slip:.1f}R"] = {
            "exp": round(m["exp"], 3), "pf": round(m["pf"], 2),
            "status": "OK" if m["exp"] > 0.15 else ("MARGINAL" if m["exp"] > 0 else "FAIL"),
        }
    report["slippage_sensitivity"] = slip_results

    # ── Mean Reversion Analysis ──
    if mr_signals:
        mr_pnl = [s["pnl_r"] for s in mr_signals]
        mr_ts = [s["ts"] for s in mr_signals]
        mr_m = metrics(mr_pnl, mr_ts)
        mr_exits = {}
        for s in mr_signals:
            et = s["exit_type"]
            mr_exits[et] = mr_exits.get(et, 0) + 1
        mr_m["exit_breakdown"] = mr_exits
        mr_m["trades_per_year"] = round(len(mr_signals) / (PERIOD_DAYS / 365.25), 1)
        report["mean_reversion"] = mr_m
    else:
        report["mean_reversion"] = {"n": 0, "trades_per_year": 0}

    # ── Role Recommendation ──
    report.update(_recommend_role(report))

    return report


def _recommend_role(report):
    """Data-driven role recommendation."""
    trend = report.get("trend_analysis", {})
    mr = report.get("mean_reversion", {})
    mfe_mae = report.get("mfe_mae_analysis", {})
    regime_bk = report.get("regime_breakdown", {})

    dyn = trend.get("dynamic", {})
    dyn_exp = dyn.get("exp", 0)
    dyn_pf = dyn.get("pf", 0)
    dyn_n = dyn.get("n", 0)
    dyn_rdd = dyn.get("rdd", 0)

    mr_exp = mr.get("exp", 0)
    mr_pf = mr.get("pf", 0)
    mr_n = mr.get("n", 0)
    mr_trades_yr = mr.get("trades_per_year", 0)

    reasons = []

    # Check CORE_PROMOTE (trend)
    if dyn_exp >= 0.15 and dyn_pf >= 1.2 and dyn_n >= 50 and dyn_rdd >= 1.0:
        # Check which regimes are positive
        positive_regimes = []
        for reg, data in regime_bk.items():
            if isinstance(data, dict) and "dynamic" in data:
                if data["dynamic"].get("exp", 0) > 0.1 and data["dynamic"].get("n", 0) >= 10:
                    positive_regimes.append(reg)
        reasons.append(f"Trend edge: exp {dyn_exp:+.3f}R, PF {dyn_pf:.2f}, {dyn_n} trades")
        reasons.append(f"Positive regimes: {', '.join(positive_regimes) if positive_regimes else 'none'}")
        return {
            "role_recommendation": "CORE_PROMOTE",
            "role_reason": "; ".join(reasons),
            "positive_regimes": positive_regimes,
        }

    # Check CHALLENGE_CANDIDATE (throughput)
    if dyn_exp >= 0.05 and dyn_pf >= 1.05 and dyn_n >= 100 and dyn_rdd >= 0.5:
        reasons.append(f"Throughput potential: exp {dyn_exp:+.3f}R, {dyn_n} trades")
        return {
            "role_recommendation": "CHALLENGE_CANDIDATE",
            "role_reason": "; ".join(reasons),
        }

    # Check MEAN_REVERSION
    if mr_exp > 0.05 and mr_pf >= 1.1 and mr_n >= 30 and mr_trades_yr >= 5:
        reasons.append(f"Mean reversion edge: exp {mr_exp:+.3f}R, PF {mr_pf:.2f}, {mr_n} trades ({mr_trades_yr}/yr)")
        return {
            "role_recommendation": "MEAN_REVERSION",
            "role_reason": "; ".join(reasons),
        }

    # Check if losers had high MFE -> partial MR signal
    if mfe_mae.get("mean_reversion_signal", False):
        reasons.append(f"MR signal: loser MFE median {mfe_mae.get('loser_mfe_median', 0):.1f}R, "
                       f"{mfe_mae.get('losers_with_mfe_above_1r', 0):.0f}% losers had MFE>1R")
        if mr_n > 0:
            reasons.append(f"MR test: exp {mr_exp:+.3f}R, {mr_n} trades")
        return {
            "role_recommendation": "MEAN_REVERSION_CANDIDATE",
            "role_reason": "; ".join(reasons),
        }

    # Check REGIME_FILTER potential
    regime_d = report.get("regime_distribution", {})
    compression_pct = regime_d.get(REGIME_COMPRESSION, 0)
    if compression_pct > 35:
        reasons.append(f"High compression: {compression_pct:.0f}% of time")
        reasons.append("Potential regime filter for core instruments")
        return {
            "role_recommendation": "REGIME_FILTER",
            "role_reason": "; ".join(reasons),
        }

    # WATCHLIST if marginal edge
    if dyn_exp > 0 and dyn_n >= 30:
        reasons.append(f"Marginal trend: exp {dyn_exp:+.3f}R, {dyn_n} trades — not enough for promotion")
        return {
            "role_recommendation": "WATCHLIST",
            "role_reason": "; ".join(reasons),
        }

    reasons.append(f"No viable edge found. Trend exp {dyn_exp:+.3f}R ({dyn_n} trades), MR exp {mr_exp:+.3f}R ({mr_n} trades)")
    return {
        "role_recommendation": "REJECT",
        "role_reason": "; ".join(reasons),
    }


# ── Display ───────────────────────────────────────────────────────────

def print_diagnostic(r):
    sym = r["symbol"]
    print(f"\n{'#' * 70}")
    print(f"  {sym} DIAGNOSTIC REPORT")
    print(f"{'#' * 70}")

    if "error" in r:
        print(f"  ERROR: {r['error']} ({r.get('bars', 0)} bars)")
        return

    print(f"  Bars: {r['bars']:,} | Period: {r['period']}")

    # Regime distribution
    print(f"\n  REGIME DISTRIBUTION:")
    for reg, pct in r.get("regime_distribution", {}).items():
        bar = "#" * int(pct / 2)
        print(f"    {reg:>12s}: {pct:5.1f}% {bar}")

    # Trend analysis
    ta = r.get("trend_analysis", {})
    if "error" in ta:
        print(f"\n  TREND ANALYSIS: {ta['error']}")
    else:
        bm = ta.get("baseline", {})
        dm = ta.get("dynamic", {})
        print(f"\n  TREND SYSTEM (SQE kernel):")
        print(f"  {'Metric':>16s} {'Baseline':>10s} {'Dynamic':>10s} {'Delta':>10s}")
        print(f"  {'-' * 50}")
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

    # Per-regime breakdown
    print(f"\n  PER-REGIME (dynamic exits):")
    for reg in [REGIME_TREND, REGIME_EXPANSION, REGIME_COMPRESSION]:
        rd = r.get("regime_breakdown", {}).get(reg, {})
        if rd.get("n", 0) == 0:
            rdyn = rd
            print(f"    {reg:>12s}: 0 trades")
            continue
        rdyn = rd.get("dynamic", {})
        print(f"    {reg:>12s}: {rdyn.get('n', 0):>3d} trades  "
              f"WR {rdyn.get('wr', 0):.0f}%  PF {rdyn.get('pf', 0):.2f}  "
              f"exp {rdyn.get('exp', 0):+.3f}R  total {rdyn.get('total_r', 0):+.1f}R  "
              f"MFE_med {rd.get('median_mfe', 0):.1f}R  MAE_med {rd.get('median_mae', 0):.1f}R")

    # Per-session
    print(f"\n  PER-SESSION (dynamic exits):")
    for sess in sorted(r.get("session_breakdown", {})):
        sd = r["session_breakdown"][sess]
        print(f"    {sess:>12s}: {sd.get('n', 0):>3d} trades  "
              f"WR {sd.get('wr', 0):.0f}%  exp {sd.get('exp', 0):+.3f}R  "
              f"total {sd.get('total_r', 0):+.1f}R")

    # Direction
    print(f"\n  PER-DIRECTION (dynamic exits):")
    for d in ["LONG", "SHORT"]:
        dd = r.get("direction_breakdown", {}).get(d, {})
        if dd:
            print(f"    {d:>12s}: {dd.get('n', 0):>3d} trades  "
                  f"WR {dd.get('wr', 0):.0f}%  exp {dd.get('exp', 0):+.3f}R  "
                  f"total {dd.get('total_r', 0):+.1f}R")

    # MFE/MAE
    mm = r.get("mfe_mae_analysis", {})
    print(f"\n  MFE/MAE ANALYSIS:")
    print(f"    MFE: mean={mm.get('mfe_mean', 0):.1f}R  med={mm.get('mfe_median', 0):.1f}R  "
          f"p25={mm.get('mfe_p25', 0):.1f}R  p75={mm.get('mfe_p75', 0):.1f}R")
    print(f"    MAE: mean={mm.get('mae_mean', 0):.1f}R  med={mm.get('mae_median', 0):.1f}R")
    if "loser_mfe_median" in mm:
        print(f"    Loser MFE median: {mm['loser_mfe_median']:.1f}R  "
              f"({mm.get('losers_with_mfe_above_1r', 0):.0f}% of losers had MFE > 1R)")
    print(f"    Mean reversion signal: {'YES' if mm.get('mean_reversion_signal') else 'NO'}")

    # Slippage
    print(f"\n  SLIPPAGE SENSITIVITY:")
    for slip_key, sd in r.get("slippage_sensitivity", {}).items():
        print(f"    {slip_key}: exp {sd['exp']:+.3f}R  PF {sd['pf']:.2f}  [{sd['status']}]")

    # Mean reversion test
    mr = r.get("mean_reversion", {})
    print(f"\n  MEAN REVERSION TEST (COMPRESSION):")
    if mr.get("n", 0) == 0:
        print(f"    No signals generated (0 trades)")
    else:
        print(f"    Trades: {mr['n']} ({mr.get('trades_per_year', 0):.0f}/yr)")
        print(f"    WR: {mr.get('wr', 0):.0f}%  PF: {mr.get('pf', 0):.2f}  "
              f"Exp: {mr.get('exp', 0):+.3f}R  Total: {mr.get('total_r', 0):+.1f}R")
        print(f"    Max DD: {mr.get('max_dd', 0):+.1f}R  R/DD: {mr.get('rdd', 0):.2f}")
        exits = mr.get("exit_breakdown", {})
        if exits:
            print(f"    Exit types: {', '.join(f'{k}={v}' for k, v in exits.items())}")

    # Yearly
    dyn_yearly = r.get("trend_analysis", {}).get("dynamic", {}).get("yearly", {})
    if dyn_yearly:
        print(f"\n  YEARLY (trend dynamic):")
        for yr in sorted(dyn_yearly):
            print(f"    {yr}: {dyn_yearly[yr]:+.1f}R")

    mr_yearly = mr.get("yearly", {})
    if mr_yearly:
        print(f"\n  YEARLY (mean reversion):")
        for yr in sorted(mr_yearly):
            print(f"    {yr}: {mr_yearly[yr]:+.1f}R")

    # VERDICT
    role = r.get("role_recommendation", "UNKNOWN")
    reason = r.get("role_reason", "")
    print(f"\n  {'=' * 60}")
    print(f"  VERDICT: [{role}]")
    print(f"  {reason}")
    if "positive_regimes" in r:
        print(f"  Positive regimes: {', '.join(r['positive_regimes'])}")
    print(f"  {'=' * 60}")


# ── Main ──────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="FX Pair Diagnostic")
    parser.add_argument("--instruments", nargs="+", default=TARGET_PAIRS)
    parser.add_argument("--skip-fetch", action="store_true")
    args = parser.parse_args()

    print("=" * 70)
    print("  FX PAIR DIAGNOSTIC — USDCHF / AUDUSD / USDCAD / NZDUSD")
    print("  Testing SQE trend + Mean Reversion + Role recommendation")
    print("=" * 70)

    cfg = load_config(CONFIG_PATH)
    setup_logging(cfg)
    base_path = Path(cfg.get("data", {}).get("base_path", "data/market_cache"))

    # Fetch data
    if not args.skip_fetch:
        print("\n  STEP 1: FETCHING DATA")
        print("-" * 70)
        for sym in args.instruments:
            print(f"\n  [{sym}]")
            ensure_data(sym, base_path)

    # Run diagnostics
    print("\n  STEP 2: RUNNING DIAGNOSTICS")
    print("-" * 70)

    all_reports = []
    for sym in args.instruments:
        print(f"\n  Diagnosing {sym}...")
        report = diagnose_pair(sym, cfg, base_path)
        all_reports.append(report)

    # Print detailed reports
    for r in all_reports:
        print_diagnostic(r)

    # Summary table
    print(f"\n{'=' * 70}")
    print(f"  SUMMARY TABLE")
    print(f"{'=' * 70}")

    print(f"\n  {'Pair':>8s} | {'Trend':>6s} {'Exp':>7s} {'PF':>5s} {'R/DD':>5s} | "
          f"{'MR':>4s} {'MR_Exp':>7s} {'MR/yr':>5s} | {'Role':>20s}")
    print(f"  {'-' * 85}")

    for r in all_reports:
        sym = r["symbol"]
        role = r.get("role_recommendation", "?")

        ta = r.get("trend_analysis", {})
        dm = ta.get("dynamic", {}) if isinstance(ta, dict) and "error" not in ta else {}
        t_n = dm.get("n", 0)
        t_exp = dm.get("exp", 0)
        t_pf = dm.get("pf", 0)
        t_rdd = dm.get("rdd", 0)

        mr = r.get("mean_reversion", {})
        m_n = mr.get("n", 0)
        m_exp = mr.get("exp", 0)
        m_yr = mr.get("trades_per_year", 0)

        print(f"  {sym:>8s} | {t_n:>6d} {t_exp:>+6.3f}R {t_pf:>5.2f} {t_rdd:>5.2f} | "
              f"{m_n:>4d} {m_exp:>+6.3f}R {m_yr:>5.0f} | {role:>20s}")

    # Actionable next steps
    print(f"\n{'=' * 70}")
    print(f"  ACTIONABLE RECOMMENDATIONS")
    print(f"{'=' * 70}")

    for r in all_reports:
        sym = r["symbol"]
        role = r.get("role_recommendation", "?")
        print(f"\n  {sym}: [{role}]")

        if role == "CORE_PROMOTE":
            pr = r.get("positive_regimes", [])
            print(f"    -> Add to core book (funded + challenge)")
            print(f"    -> Enable regimes: {', '.join(pr)}")
            print(f"    -> Use dynamic exits")

        elif role == "CHALLENGE_CANDIDATE":
            print(f"    -> Add to throughput book (challenge only)")
            print(f"    -> Lower risk multiplier (0.5-0.7x)")
            print(f"    -> Cap at 1-2 trades/day")

        elif role in ("MEAN_REVERSION", "MEAN_REVERSION_CANDIDATE"):
            mr = r.get("mean_reversion", {})
            print(f"    -> Build mean reversion module (like EURUSD)")
            print(f"    -> COMPRESSION regime only")
            print(f"    -> Fixed TP (1.0R), tight SL, time stop")
            if mr.get("n", 0) > 0:
                print(f"    -> Current MR: {mr['n']} trades, exp {mr.get('exp', 0):+.3f}R")

        elif role == "REGIME_FILTER":
            rd = r.get("regime_distribution", {})
            print(f"    -> Don't trade directly")
            print(f"    -> Use regime state as confidence modifier")
            print(f"    -> Compression {rd.get(REGIME_COMPRESSION, 0):.0f}% of time")

        elif role == "WATCHLIST":
            print(f"    -> Marginal edge, revisit in next iteration")
            print(f"    -> May improve with instrument-specific tuning")

        elif role == "REJECT":
            print(f"    -> No viable role found")
            print(f"    -> Don't add to portfolio")

    # Save reports
    report_dir = Path("reports/latest")
    report_dir.mkdir(parents=True, exist_ok=True)
    save_data = []
    for r in all_reports:
        rd = {k: v for k, v in r.items() if k not in ("timestamps", "dynamic_pnl")}
        save_data.append(rd)

    report_path = report_dir / "fx_pair_diagnostic.json"
    with open(report_path, "w") as f:
        json.dump(save_data, f, indent=2, default=str)
    print(f"\n  Results saved to {report_path}")
    print("=" * 70)


if __name__ == "__main__":
    main()
