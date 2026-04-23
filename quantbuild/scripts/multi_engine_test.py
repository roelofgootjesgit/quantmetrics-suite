"""
Multi-Engine Portfolio Test — the decisive funded + challenge comparison.

Tests 3 engines together:
  1. CORE TREND (XAU + GBP + JPY) — existing SQE kernel
  2. THROUGHPUT (NAS100 TREND) — with improved exits
  3. MEAN REVERSION (EURUSD COMPRESSION) — new engine

Scenarios tested:
  A. Core only (baseline)
  B. Core + NAS100 (throughput)
  C. Core + EURUSD MR (stability)
  D. Core + NAS100 + EURUSD MR (full stack)

For each: challenge pass rate + funded monthly return.

Usage:
    python scripts/multi_engine_test.py
"""
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
from src.quantbuild.io.parquet_loader import load_parquet, save_parquet, _fetch_dukascopy
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
PROFILES_PATH = "configs/instruments/instrument_profiles.yaml"
PERIOD_DAYS = 1825


# ── SQE Exit Functions (from candidate_instrument_test) ──────────────

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
                return 1.0 * 0.5 + max(0, peak - 1.5) * 0.5
    if partial_filled:
        return max(0, 1.0 * 0.5 + (peak - 1.5) * 0.5)
    return 0.0


def exit_nas_improved(exc, sl_r=1.0):
    """NAS100 improved exit: partial TP at 0.5R (50%), trail rest from 1R, time stop 20 bars."""
    partial_taken = False
    peak = 0.0
    for bar_idx, (fav, adv) in enumerate(exc):
        if adv >= sl_r:
            if partial_taken:
                return 0.5 * 0.5 + (-sl_r) * 0.5
            return -sl_r

        if not partial_taken and fav >= 0.5:
            partial_taken = True
            peak = fav
            continue

        if partial_taken:
            peak = max(peak, fav)
            drawback = peak - fav
            if drawback >= 1.0:
                return 0.5 * 0.5 + max(0, peak - 1.0) * 0.5

        # Time stop at 20 bars
        if bar_idx >= 20:
            if partial_taken:
                return 0.5 * 0.5 + fav * 0.5
            return fav if fav > 0 else min(0, fav)

    if partial_taken:
        last_fav = exc[-1][0] if exc else 0
        return 0.5 * 0.5 + last_fav * 0.5
    return 0.0


# ── Signal Generation ────────────────────────────────────────────────

def generate_sqe_signals(symbol, cfg, inst_profile, base_path, start, end, use_nas_exit=False):
    """Generate SQE (trend) signals for a symbol."""
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
    inst_regimes = inst_profile.get("regimes", {})
    exp_sessions = inst_profile.get("expansion_sessions")
    exp_min_hour = inst_profile.get("expansion_min_hour_utc")
    session_mode = inst_profile.get("session_mode", "extended")

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
            is_exp_ny = regime == REGIME_EXPANSION and session in ("New York", "Overlap") and ts.hour >= 10

            if use_nas_exit:
                pnl = exit_nas_improved(exc)
            else:
                pnl = exit_dynamic(exc, is_exp_ny)

            signals.append({
                "ts": ts, "symbol": symbol, "direction": direction,
                "regime": regime, "session": session, "pnl_r": pnl,
                "engine": "sqe_trend",
                "asset_class": inst_profile.get("asset_class", "unknown"),
            })

    return signals


def generate_mr_signals(cfg, base_path, start, end):
    """Generate mean reversion signals for EURUSD."""
    symbol = "EURUSD"
    data = load_parquet(base_path, symbol, "15m", start=start, end=end)
    if data.empty or len(data) < 200:
        return []
    data = data.sort_index()

    data_1h = load_parquet(base_path, symbol, "1h", start=start, end=end)
    if not data_1h.empty:
        data_1h = data_1h.sort_index()

    detector = RegimeDetector(config=cfg.get("regime", {}))
    regime_series = detector.classify(data, data_1h if not data_1h.empty else None)

    mr_cfg = {**DEFAULT_MR_CONFIG}

    long_e = run_mr_conditions(data, "LONG", mr_cfg, regime_series)
    short_e = run_mr_conditions(data, "SHORT", mr_cfg, regime_series)

    sim_cache = _prepare_sim_cache(data)

    signals = []
    for i in range(1, len(data) - 1):
        for direction, mask in [("LONG", long_e), ("SHORT", short_e)]:
            if not mask.iloc[i]:
                continue
            ts = data.index[i]
            regime = regime_series.iloc[i] if i < len(regime_series) else REGIME_COMPRESSION
            session = session_from_timestamp(ts, mode="extended")

            result = simulate_mr_trade(
                sim_cache, i, direction,
                tp_r=mr_cfg["tp_r"], sl_r=mr_cfg["sl_r"],
                time_stop_bars=mr_cfg["time_stop_bars"],
            )

            signals.append({
                "ts": ts, "symbol": symbol, "direction": direction,
                "regime": regime, "session": session,
                "pnl_r": result["pnl_r"],
                "mfe": result["mfe"], "mae": result["mae"],
                "bars_held": result["bars_held"],
                "exit_type": result["exit_type"],
                "engine": "mean_reversion",
                "asset_class": "fx_major",
            })

    return signals


# ── Metrics ──────────────────────────────────────────────────────────

def compute_metrics(signals, label=""):
    if not signals:
        return {"label": label, "trades": 0}
    pnl = np.array([s["pnl_r"] for s in signals])
    wins = pnl[pnl > 0]
    losses = pnl[pnl < 0]
    gw = wins.sum() if len(wins) else 0
    gl = abs(losses.sum()) if len(losses) else 0.001
    eq = np.cumsum(pnl)
    peak = np.maximum.accumulate(eq)
    dd = eq - peak
    return {
        "label": label,
        "trades": len(pnl),
        "wr": 100 * len(wins) / len(pnl),
        "pf": gw / gl,
        "exp": float(pnl.mean()),
        "total_r": float(pnl.sum()),
        "max_dd": float(dd.min()),
        "rdd": float(eq[-1] / abs(dd.min())) if dd.min() < 0 else 0,
        "trades_yr": len(pnl) / 5,
    }


def print_metrics(m):
    if m["trades"] == 0:
        print(f"  {m['label']}: NO TRADES")
        return
    print(f"  {m['label']}:")
    print(f"    Trades: {m['trades']} ({m['trades_yr']:.0f}/yr)  WR: {m['wr']:.0f}%  "
          f"PF: {m['pf']:.2f}  Exp: {m['exp']:+.3f}R")
    print(f"    Total: {m['total_r']:+.1f}R  DD: {m['max_dd']:.1f}R  R/DD: {m['rdd']:.2f}")


# ── FTMO Monte Carlo ────────────────────────────────────────────────

def ftmo_monte_carlo(signals, n_sims=5000, n_days=30, target=10.0, max_dd=10.0, base_risk=1.5):
    if not signals:
        return {"pass_rate": 0, "avg_days": 0}
    pnl_pool = np.array([s["pnl_r"] for s in signals])
    avg_per_day = len(pnl_pool) / (5 * 250)

    passed = 0
    pass_days = []
    for _ in range(n_sims):
        eq = 0.0
        peak_eq = 0.0
        sim_passed = False
        for day in range(1, n_days + 1):
            trades_today = max(0, np.random.poisson(avg_per_day * 1.5))
            for _ in range(trades_today):
                raw = pnl_pool[np.random.randint(len(pnl_pool))]
                eq += raw * base_risk - 0.065 * base_risk
                peak_eq = max(peak_eq, eq)
                if peak_eq - eq >= max_dd:
                    break
            if peak_eq - eq >= max_dd:
                break
            if eq >= target:
                passed += 1
                pass_days.append(day)
                sim_passed = True
                break

    return {
        "pass_rate": 100 * passed / n_sims,
        "avg_days": float(np.mean(pass_days)) if pass_days else 0,
    }


# ── Main ─────────────────────────────────────────────────────────────

def main():
    print("=" * 70)
    print("  MULTI-ENGINE PORTFOLIO TEST")
    print("  Core Trend + NAS100 Throughput + EURUSD Mean Reversion")
    print("=" * 70)

    cfg = load_config(CONFIG_PATH)
    setup_logging(cfg)

    with open(PROFILES_PATH) as f:
        profiles = yaml.safe_load(f)

    inst_profiles = profiles["instruments"]
    base_path = Path(cfg.get("data", {}).get("base_path", "data/market_cache"))
    end = datetime.now()
    start = end - timedelta(days=PERIOD_DAYS)

    # ── Generate all signals ─────────────────────────────────
    print("\n  Generating signals...")

    # Core instruments (SQE trend)
    core_signals = []
    for sym in ["XAUUSD", "GBPUSD", "USDJPY"]:
        inst = inst_profiles.get(sym, {})
        sigs = generate_sqe_signals(sym, cfg, inst, base_path, start, end)
        print(f"    {sym}: {len(sigs)} signals")
        core_signals.extend(sigs)

    # NAS100 with improved exits
    nas_inst = inst_profiles.get("NAS100", {})
    nas_signals = generate_sqe_signals("NAS100", cfg, nas_inst, base_path, start, end, use_nas_exit=True)
    print(f"    NAS100 (improved exit): {len(nas_signals)} signals")

    # NAS100 with baseline exits for comparison
    nas_baseline = generate_sqe_signals("NAS100", cfg, nas_inst, base_path, start, end, use_nas_exit=False)
    print(f"    NAS100 (baseline exit): {len(nas_baseline)} signals")

    # EURUSD mean reversion
    mr_signals = generate_mr_signals(cfg, base_path, start, end)
    print(f"    EURUSD MR: {len(mr_signals)} signals")

    # ── Per-engine analysis ──────────────────────────────────
    print("\n" + "=" * 70)
    print("  PER-ENGINE BREAKDOWN")
    print("=" * 70)

    for sym in ["XAUUSD", "GBPUSD", "USDJPY"]:
        sym_sigs = [s for s in core_signals if s["symbol"] == sym]
        print_metrics(compute_metrics(sym_sigs, f"{sym} (SQE Trend)"))

    print_metrics(compute_metrics(nas_baseline, "NAS100 (baseline exit)"))
    print_metrics(compute_metrics(nas_signals, "NAS100 (improved exit)"))

    # NAS100 exit improvement delta
    if nas_baseline and nas_signals:
        base_total = sum(s["pnl_r"] for s in nas_baseline)
        imp_total = sum(s["pnl_r"] for s in nas_signals)
        print(f"    NAS100 exit delta: {imp_total - base_total:+.1f}R")

    print_metrics(compute_metrics(mr_signals, "EURUSD (Mean Reversion)"))

    # EURUSD MR breakdown
    if mr_signals:
        exit_types = {}
        for s in mr_signals:
            et = s.get("exit_type", "unknown")
            exit_types.setdefault(et, []).append(s["pnl_r"])
        print(f"    Exit type breakdown:")
        for et, pnls in sorted(exit_types.items()):
            print(f"      {et:>6s}: {len(pnls)} trades  exp {np.mean(pnls):+.3f}R  total {sum(pnls):+.1f}R")

    # ── Scenario Comparison ──────────────────────────────────
    print("\n" + "=" * 70)
    print("  SCENARIO COMPARISON")
    print("=" * 70)

    scenarios = {
        "A: Core only": core_signals,
        "B: Core + NAS100": core_signals + nas_signals,
        "C: Core + EURUSD MR": core_signals + mr_signals,
        "D: Core + NAS + EUR": core_signals + nas_signals + mr_signals,
    }

    scenario_metrics = {}
    for name, sigs in scenarios.items():
        m = compute_metrics(sigs, name)
        scenario_metrics[name] = m
        print_metrics(m)

    # ── FTMO Challenge Comparison ────────────────────────────
    print("\n" + "=" * 70)
    print("  FTMO CHALLENGE (5,000 simulations per scenario)")
    print("=" * 70)

    for name, sigs in scenarios.items():
        ftmo = ftmo_monte_carlo(sigs, n_sims=5000)
        print(f"  {name}:")
        print(f"    Pass rate: {ftmo['pass_rate']:.1f}%  Avg days: {ftmo['avg_days']:.0f}")

    # ── Funded Projection ────────────────────────────────────
    print("\n" + "=" * 70)
    print("  FUNDED PROJECTION (per year at 0.75% risk)")
    print("=" * 70)

    risk_funded = 0.75
    for name, sigs in scenarios.items():
        if not sigs:
            continue
        m = scenario_metrics[name]
        yearly_r = m["trades_yr"] * m["exp"]
        yearly_pct = yearly_r * risk_funded
        monthly_pct = yearly_pct / 12
        print(f"  {name}:")
        print(f"    Trades/yr: {m['trades_yr']:.0f}  Exp: {m['exp']:+.3f}R  "
              f"Yearly: {yearly_pct:+.1f}%  Monthly: {monthly_pct:+.2f}%")

    # ── Head-to-Head ─────────────────────────────────────────
    print("\n" + "=" * 70)
    print("  HEAD-TO-HEAD SUMMARY")
    print("=" * 70)

    header = f"  {'Scenario':<25s} {'Trades':>7s} {'Exp':>7s} {'Total':>8s} {'DD':>7s} {'R/DD':>6s} {'Tr/yr':>6s}"
    print(header)
    print("  " + "-" * 67)
    for name in scenarios:
        m = scenario_metrics[name]
        if m["trades"] == 0:
            continue
        print(f"  {name:<25s} {m['trades']:>7d} {m['exp']:>+6.3f} {m['total_r']:>+7.1f} "
              f"{m['max_dd']:>+6.1f} {m['rdd']:>6.2f} {m['trades_yr']:>5.0f}")

    print("\n" + "=" * 70)
    print("  Done.")
    print("=" * 70)


if __name__ == "__main__":
    main()
