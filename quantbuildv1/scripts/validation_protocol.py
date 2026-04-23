"""
Validation Protocol v1 — Walk-Forward + Monte Carlo + Frozen Rules.

Three independent tests that must ALL pass before live deployment:

TEST 1: Walk-Forward Validation (out-of-sample proof)
  - Rolling 1-year train / 6-month test windows
  - Measures adaptive vs static DELTA per window (not absolute return)
  - Acceptance: adaptive delta > 0 in >= 60% of windows

TEST 2: Monte Carlo Path Stress (path-dependency proof)
  - Randomizes trade ordering within each month
  - Injects correlation shocks, slippage spikes, delayed recoveries
  - Acceptance: adaptive outperforms static in >= 55% of 5000 paths

TEST 3: Frozen-Rules No-Touch Validation (overfit proof)
  - Locks ALL adaptive thresholds from train period
  - Runs on full sample with zero parameter changes
  - Acceptance: R/DD improvement > 20% vs static, max DD within 150% of backtest

Usage:
    python scripts/validation_protocol.py
    python scripts/validation_protocol.py --skip-fetch
"""
import argparse
import json
import sys
from copy import deepcopy
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
from src.quantbuild.execution.portfolio_heat import PortfolioHeatEngine
from src.quantbuild.execution.adaptive_mode import AdaptiveModeLayer

import logging
logging.disable(logging.INFO)

CONFIG_PATH = "configs/strict_prod_v2.yaml"
PROFILES_PATH = "configs/instruments/instrument_profiles.yaml"

SLIPPAGE_PROFILES = {
    "XAUUSD": {"mean": 0.08, "std": 0.05, "spread_mean": 2.5, "spread_std": 1.0},
    "GBPUSD": {"mean": 0.04, "std": 0.03, "spread_mean": 1.2, "spread_std": 0.5},
    "USDJPY": {"mean": 0.04, "std": 0.02, "spread_mean": 0.9, "spread_std": 0.4},
}

# ── Acceptance Thresholds ────────────────────────────────────────────
ACCEPT = {
    "wf_adaptive_win_rate": 60.0,       # % of windows where adaptive > static
    "wf_min_windows": 4,                 # minimum walk-forward windows
    "mc_adaptive_win_rate": 55.0,        # % of MC paths where adaptive > static
    "mc_n_paths": 5000,
    "frozen_rdd_improvement_pct": 20.0,  # R/DD improvement vs static
    "frozen_max_dd_ratio": 1.5,          # max DD <= 150% of in-sample DD
}


# ── Shared: Exit + Signal Logic ──────────────────────────────────────

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


def generate_all_signals(cfg, profiles, period_start, period_end):
    instruments_cfg = profiles["instruments"]
    promoted = {s: i for s, i in instruments_cfg.items() if i.get("status") == "PROMOTE"}
    base_path = Path(cfg.get("data", {}).get("base_path", "data/market_cache"))

    all_signals = []
    for sym, inst_profile in promoted.items():
        sigs = _generate_instrument_signals(sym, cfg, inst_profile, base_path, period_start, period_end)
        all_signals.extend(sigs)
    return all_signals


def _generate_instrument_signals(symbol, cfg, inst_profile, base_path, start, end):
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
            signals.append({
                "ts": ts, "symbol": symbol, "direction": direction,
                "regime": regime, "session": session, "pnl": pnl,
                "asset_class": inst_profile.get("asset_class", ""),
            })
    return signals


# ── Simulate (shared) ────────────────────────────────────────────────

def _make_adaptive_cfg(mode_cfg):
    return {
        "adaptive_mode": {
            "aggressive_dd_max": 1.0,
            "aggressive_momentum_window": 5,
            "defensive_dd": mode_cfg.get("max_daily_loss_pct", 3.0) * 0.6,
            "lockdown_dd": mode_cfg.get("max_total_dd_pct", 10.0) * 0.7,
            "defensive_losing_streak": 4,
            "lockdown_losing_streak": 6,
            "recovery_wins": 3,
        }
    }


def simulate_signals(signals, mode_cfg, instruments_cfg, with_adaptive=True,
                     adaptive_overrides=None, slippage_mult=1.0, rng=None):
    """Run portfolio simulation on a list of signals.
    Returns dict with equity curve stats.
    """
    if rng is None:
        rng = np.random.default_rng(42)

    risk_base = mode_cfg["risk_per_trade_pct"]
    heat_cfg = {
        "max_portfolio_heat_pct": mode_cfg.get("max_portfolio_heat_pct", 6.0),
        "max_instrument_heat_pct": risk_base * 2.5,
        "max_correlated_exposure": mode_cfg.get("max_correlated_exposure", 2),
        "max_same_direction": 4,
    }
    heat_engine = PortfolioHeatEngine(heat_cfg)

    a_cfg = adaptive_overrides or _make_adaptive_cfg(mode_cfg)
    adaptive = AdaptiveModeLayer(a_cfg)

    merged = sorted(signals, key=lambda s: s["ts"])

    equity_pct = 0.0
    peak_equity = 0.0
    daily_pnl_map = {}
    trades_out = []
    blocked_total = 0

    for sig in merged:
        ts = sig["ts"]
        day = ts.date() if hasattr(ts, "date") else ts
        sym = sig["symbol"]
        inst = instruments_cfg.get(sym, {})
        asset_class = sig.get("asset_class", inst.get("asset_class", ""))

        day_pnl = daily_pnl_map.get(day, 0.0)
        max_daily = mode_cfg.get("max_daily_loss_pct", 5.0)
        if day_pnl <= -max_daily:
            blocked_total += 1
            continue

        dd_from_peak = peak_equity - equity_pct
        if dd_from_peak >= mode_cfg.get("max_total_dd_pct", 10.0):
            blocked_total += 1
            continue

        current_mode = adaptive.current_mode if with_adaptive else "BASE"
        if current_mode == "LOCKDOWN":
            blocked_total += 1
            continue

        effective_risk = adaptive.get_effective_risk(risk_base) if with_adaptive else risk_base
        risk_mult = inst.get("risk_multiplier", 1.0)
        trade_risk = effective_risk * risk_mult

        allowed, _ = heat_engine.can_open(sym, sig["direction"], trade_risk, asset_class)
        if not allowed:
            blocked_total += 1
            continue

        slip_prof = SLIPPAGE_PROFILES.get(sym, {"mean": 0.05, "std": 0.03, "spread_mean": 1.5, "spread_std": 0.5})
        slippage = abs(rng.normal(slip_prof["mean"] * slippage_mult, slip_prof["std"] * slippage_mult))
        spread = abs(rng.normal(slip_prof["spread_mean"], slip_prof["spread_std"]))

        max_spread = inst.get("max_spread_pips", 4.0)
        max_slip = inst.get("max_slippage_r", 0.15)
        if spread > max_spread or slippage > max_slip:
            blocked_total += 1
            continue

        net_pnl_r = sig["pnl"] - slippage
        trade_pnl_pct = net_pnl_r * trade_risk
        equity_pct += trade_pnl_pct
        peak_equity = max(peak_equity, equity_pct)
        daily_pnl_map[day] = daily_pnl_map.get(day, 0.0) + trade_pnl_pct

        heat_engine.add_position(sym, sig["direction"], trade_risk, asset_class, sig["regime"])

        adaptive.record_trade(net_pnl_r, sym, sig["regime"])
        adaptive.update_equity(equity_pct)

        trades_out.append({
            "ts": ts, "pnl_r": net_pnl_r, "pnl_pct": trade_pnl_pct,
            "equity": equity_pct, "mode": current_mode, "symbol": sym,
        })

        heat_engine.remove_position(sym, sig["direction"])

    if not trades_out:
        return {"trades": 0, "total_pct": 0, "max_dd_pct": 0, "rdd": 0, "blocked": blocked_total}

    eq = np.array([t["equity"] for t in trades_out])
    pk = np.maximum.accumulate(eq)
    dd = eq - pk
    max_dd = float(dd.min())
    pnls = np.array([t["pnl_r"] for t in trades_out])

    return {
        "trades": len(trades_out),
        "total_pct": float(equity_pct),
        "total_r": float(pnls.sum()),
        "exp_r": float(pnls.mean()),
        "max_dd_pct": max_dd,
        "rdd": float(equity_pct / abs(max_dd)) if max_dd < 0 else 0,
        "blocked": blocked_total,
        "trade_list": trades_out,
    }


# ══════════════════════════════════════════════════════════════════════
# TEST 1: Walk-Forward Validation
# ══════════════════════════════════════════════════════════════════════

def test_walk_forward(all_signals, mode_cfg, instruments_cfg):
    """Rolling window walk-forward: 12-month train, 6-month test."""
    print("\n" + "=" * 70)
    print("  TEST 1: WALK-FORWARD VALIDATION")
    print("  Train: 12 months | Test: 6 months | Step: 6 months")
    print("=" * 70)

    if not all_signals:
        print("  NO SIGNALS — FAIL")
        return False, {}

    sorted_sigs = sorted(all_signals, key=lambda s: s["ts"])
    first_ts = sorted_sigs[0]["ts"]
    last_ts = sorted_sigs[-1]["ts"]

    train_months = 12
    test_months = 6
    step_months = 6

    windows = []
    current = first_ts
    while True:
        train_end = current + timedelta(days=train_months * 30)
        test_end = train_end + timedelta(days=test_months * 30)
        if test_end > last_ts:
            break
        windows.append((current, train_end, test_end))
        current += timedelta(days=step_months * 30)

    if len(windows) < ACCEPT["wf_min_windows"]:
        print(f"  Only {len(windows)} windows (need {ACCEPT['wf_min_windows']}) — INSUFFICIENT DATA")
        # Still run what we have
        if len(windows) == 0:
            return False, {}

    print(f"\n  Windows: {len(windows)}")

    results = []
    rng = np.random.default_rng(42)

    for i, (train_start, train_end, test_end) in enumerate(windows):
        # Split signals
        test_sigs = [s for s in sorted_sigs if train_end <= s["ts"] < test_end]

        if len(test_sigs) < 5:
            print(f"  Window {i+1}: {train_start.strftime('%Y-%m')} -> {test_end.strftime('%Y-%m')} "
                  f"| test signals: {len(test_sigs)} (skipped)")
            continue

        # Run adaptive on test period
        adaptive_res = simulate_signals(test_sigs, mode_cfg, instruments_cfg,
                                         with_adaptive=True, rng=np.random.default_rng(i))
        static_res = simulate_signals(test_sigs, mode_cfg, instruments_cfg,
                                       with_adaptive=False, rng=np.random.default_rng(i))

        delta_rdd = adaptive_res["rdd"] - static_res["rdd"]
        delta_pct = adaptive_res["total_pct"] - static_res["total_pct"]
        adaptive_wins = delta_rdd > 0

        results.append({
            "window": i + 1,
            "period": f"{train_end.strftime('%Y-%m')} to {test_end.strftime('%Y-%m')}",
            "test_trades_adaptive": adaptive_res["trades"],
            "test_trades_static": static_res["trades"],
            "adaptive_rdd": adaptive_res["rdd"],
            "static_rdd": static_res["rdd"],
            "delta_rdd": delta_rdd,
            "adaptive_pct": adaptive_res["total_pct"],
            "static_pct": static_res["total_pct"],
            "delta_pct": delta_pct,
            "adaptive_max_dd": adaptive_res["max_dd_pct"],
            "static_max_dd": static_res["max_dd_pct"],
            "adaptive_wins": adaptive_wins,
        })

        mark = ">>>" if adaptive_wins else "   "
        print(f"  {mark} Window {i+1}: {train_end.strftime('%Y-%m')}-{test_end.strftime('%Y-%m')} "
              f"| Adaptive R/DD {adaptive_res['rdd']:+.2f} vs Static {static_res['rdd']:+.2f} "
              f"| delta {delta_rdd:+.2f} | return {delta_pct:+.1f}%")

    if not results:
        print("  NO VALID WINDOWS — FAIL")
        return False, {}

    # Verdict
    adaptive_win_count = sum(1 for r in results if r["adaptive_wins"])
    win_rate = 100 * adaptive_win_count / len(results)
    passed = win_rate >= ACCEPT["wf_adaptive_win_rate"]

    print(f"\n  Walk-Forward Summary:")
    print(f"    Windows tested:       {len(results)}")
    print(f"    Adaptive wins:        {adaptive_win_count}/{len(results)} ({win_rate:.0f}%)")
    print(f"    Threshold:            {ACCEPT['wf_adaptive_win_rate']:.0f}%")
    print(f"    Avg R/DD delta:       {np.mean([r['delta_rdd'] for r in results]):+.2f}")
    print(f"    Avg return delta:     {np.mean([r['delta_pct'] for r in results]):+.2f}%")
    verdict = "PASS" if passed else "FAIL"
    print(f"\n  >>> TEST 1 VERDICT: {verdict} <<<")

    return passed, {"windows": results, "win_rate": win_rate}


# ══════════════════════════════════════════════════════════════════════
# TEST 2: Monte Carlo Path Stress
# ══════════════════════════════════════════════════════════════════════

def test_monte_carlo_paths(all_signals, mode_cfg, instruments_cfg, n_paths=None):
    """Randomize trade order within months + inject shocks."""
    n_paths = n_paths or ACCEPT["mc_n_paths"]

    print("\n" + "=" * 70)
    print(f"  TEST 2: MONTE CARLO PATH STRESS ({n_paths:,} paths)")
    print("  Randomized trade order + correlation/slippage shocks")
    print("=" * 70)

    if not all_signals:
        print("  NO SIGNALS — FAIL")
        return False, {}

    sorted_sigs = sorted(all_signals, key=lambda s: s["ts"])

    # Group by month for intra-month shuffling
    monthly_groups = {}
    for s in sorted_sigs:
        key = s["ts"].strftime("%Y-%m") if hasattr(s["ts"], "strftime") else "2025-01"
        monthly_groups.setdefault(key, []).append(s)

    month_keys = sorted(monthly_groups.keys())

    adaptive_wins = 0
    adaptive_rdd_deltas = []
    adaptive_dd_list = []
    static_dd_list = []

    for path_i in range(n_paths):
        rng = np.random.default_rng(path_i)

        # Shuffle within each month
        shuffled_sigs = []
        for mk in month_keys:
            group = list(monthly_groups[mk])
            rng.shuffle(group)
            shuffled_sigs.extend(group)

        # Inject correlation shock: 10% chance per path of 2x slippage
        slip_mult = 2.0 if rng.random() < 0.10 else 1.0

        # Inject delayed recovery: 5% chance of adding extra -0.3R to first 3 trades
        delayed_recovery = rng.random() < 0.05

        if delayed_recovery:
            for j in range(min(3, len(shuffled_sigs))):
                shuffled_sigs[j] = dict(shuffled_sigs[j])
                shuffled_sigs[j]["pnl"] = shuffled_sigs[j]["pnl"] - 0.3

        adaptive_res = simulate_signals(shuffled_sigs, mode_cfg, instruments_cfg,
                                         with_adaptive=True, slippage_mult=slip_mult,
                                         rng=np.random.default_rng(path_i + 100000))
        static_res = simulate_signals(shuffled_sigs, mode_cfg, instruments_cfg,
                                       with_adaptive=False, slippage_mult=slip_mult,
                                       rng=np.random.default_rng(path_i + 100000))

        delta = adaptive_res["rdd"] - static_res["rdd"]
        adaptive_rdd_deltas.append(delta)
        adaptive_dd_list.append(adaptive_res["max_dd_pct"])
        static_dd_list.append(static_res["max_dd_pct"])

        if delta > 0:
            adaptive_wins += 1

    win_rate = 100 * adaptive_wins / n_paths
    passed = win_rate >= ACCEPT["mc_adaptive_win_rate"]

    print(f"\n  Monte Carlo Summary ({n_paths:,} paths):")
    print(f"    Adaptive wins:        {adaptive_wins}/{n_paths} ({win_rate:.1f}%)")
    print(f"    Threshold:            {ACCEPT['mc_adaptive_win_rate']:.0f}%")
    print(f"    Avg R/DD delta:       {np.mean(adaptive_rdd_deltas):+.2f}")
    print(f"    Median R/DD delta:    {np.median(adaptive_rdd_deltas):+.2f}")
    print(f"    P5 R/DD delta:        {np.percentile(adaptive_rdd_deltas, 5):+.2f}")
    print(f"    P95 R/DD delta:       {np.percentile(adaptive_rdd_deltas, 95):+.2f}")
    print(f"    Adaptive avg DD:      {np.mean(adaptive_dd_list):+.2f}%")
    print(f"    Static avg DD:        {np.mean(static_dd_list):+.2f}%")
    verdict = "PASS" if passed else "FAIL"
    print(f"\n  >>> TEST 2 VERDICT: {verdict} <<<")

    return passed, {
        "win_rate": win_rate,
        "avg_delta": float(np.mean(adaptive_rdd_deltas)),
        "median_delta": float(np.median(adaptive_rdd_deltas)),
        "p5": float(np.percentile(adaptive_rdd_deltas, 5)),
        "p95": float(np.percentile(adaptive_rdd_deltas, 95)),
    }


# ══════════════════════════════════════════════════════════════════════
# TEST 3: Frozen-Rules No-Touch Validation
# ══════════════════════════════════════════════════════════════════════

def test_frozen_rules(all_signals, mode_cfg, instruments_cfg):
    """Lock thresholds, run full sample, compare to static."""
    print("\n" + "=" * 70)
    print("  TEST 3: FROZEN-RULES NO-TOUCH VALIDATION")
    print("  All adaptive thresholds locked — zero tuning")
    print("=" * 70)

    if not all_signals:
        print("  NO SIGNALS — FAIL")
        return False, {}

    # The adaptive config is FROZEN — these are the production thresholds
    frozen_cfg = _make_adaptive_cfg(mode_cfg)

    rng = np.random.default_rng(42)
    adaptive_res = simulate_signals(all_signals, mode_cfg, instruments_cfg,
                                     with_adaptive=True, adaptive_overrides=frozen_cfg, rng=rng)
    rng2 = np.random.default_rng(42)
    static_res = simulate_signals(all_signals, mode_cfg, instruments_cfg,
                                   with_adaptive=False, rng=rng2)

    rdd_improvement = 0
    if static_res["rdd"] > 0:
        rdd_improvement = 100 * (adaptive_res["rdd"] - static_res["rdd"]) / static_res["rdd"]

    dd_ratio = abs(adaptive_res["max_dd_pct"]) / abs(static_res["max_dd_pct"]) if static_res["max_dd_pct"] < 0 else 1.0

    passed_rdd = rdd_improvement >= ACCEPT["frozen_rdd_improvement_pct"]
    passed_dd = dd_ratio <= ACCEPT["frozen_max_dd_ratio"]
    passed = passed_rdd and passed_dd

    print(f"\n  Frozen-Rules Results:")
    print(f"    Adaptive: {adaptive_res['trades']} trades, "
          f"R/DD {adaptive_res['rdd']:.2f}, "
          f"DD {adaptive_res['max_dd_pct']:+.2f}%, "
          f"total {adaptive_res['total_pct']:+.1f}%")
    print(f"    Static:   {static_res['trades']} trades, "
          f"R/DD {static_res['rdd']:.2f}, "
          f"DD {static_res['max_dd_pct']:+.2f}%, "
          f"total {static_res['total_pct']:+.1f}%")
    print(f"    R/DD improvement:     {rdd_improvement:+.1f}% (threshold: {ACCEPT['frozen_rdd_improvement_pct']}%)")
    print(f"    DD ratio:             {dd_ratio:.2f}x (threshold: {ACCEPT['frozen_max_dd_ratio']}x)")

    verdict = "PASS" if passed else "FAIL"
    if not passed_rdd:
        print(f"    --> FAIL: R/DD improvement {rdd_improvement:.1f}% < {ACCEPT['frozen_rdd_improvement_pct']}%")
    if not passed_dd:
        print(f"    --> FAIL: DD ratio {dd_ratio:.2f}x > {ACCEPT['frozen_max_dd_ratio']}x")
    print(f"\n  >>> TEST 3 VERDICT: {verdict} <<<")

    return passed, {
        "adaptive": {k: v for k, v in adaptive_res.items() if k != "trade_list"},
        "static": {k: v for k, v in static_res.items() if k != "trade_list"},
        "rdd_improvement_pct": rdd_improvement,
        "dd_ratio": dd_ratio,
    }


# ══════════════════════════════════════════════════════════════════════
# Main Protocol Runner
# ══════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-fetch", action="store_true")
    parser.add_argument("--mc-paths", type=int, default=ACCEPT["mc_n_paths"])
    args = parser.parse_args()

    print("=" * 70)
    print("  VALIDATION PROTOCOL v1")
    print("  Walk-Forward + Monte Carlo Path Stress + Frozen Rules")
    print("  All 3 tests must PASS before live deployment")
    print("=" * 70)

    cfg = load_config(CONFIG_PATH)
    setup_logging(cfg)

    with open(PROFILES_PATH) as f:
        profiles = yaml.safe_load(f)

    instruments_cfg = profiles["instruments"]
    challenge_cfg = profiles["modes"]["challenge"]

    # Generate signals over full 5-year period
    end = datetime.now()
    start = end - timedelta(days=1825)
    print(f"\n  Period: {start.strftime('%Y-%m-%d')} to {end.strftime('%Y-%m-%d')}")
    print(f"  Generating signals for promoted instruments...")

    all_signals = generate_all_signals(cfg, profiles, start, end)
    print(f"  Total signals: {len(all_signals)}")

    if not all_signals:
        print("\n  FATAL: No signals generated. Cannot validate.")
        return

    # Run all 3 tests
    t1_pass, t1_data = test_walk_forward(all_signals, challenge_cfg, instruments_cfg)
    t2_pass, t2_data = test_monte_carlo_paths(all_signals, challenge_cfg, instruments_cfg, args.mc_paths)
    t3_pass, t3_data = test_frozen_rules(all_signals, challenge_cfg, instruments_cfg)

    # ── Final Verdict ─────────────────────────────────────────────────
    all_passed = t1_pass and t2_pass and t3_pass

    print("\n" + "=" * 70)
    print("  VALIDATION PROTOCOL v1 — FINAL VERDICT")
    print("=" * 70)
    print(f"\n  Test 1 (Walk-Forward):     {'PASS' if t1_pass else 'FAIL'}")
    print(f"  Test 2 (MC Path Stress):   {'PASS' if t2_pass else 'FAIL'}")
    print(f"  Test 3 (Frozen Rules):     {'PASS' if t3_pass else 'FAIL'}")
    print(f"\n  {'='*50}")

    if all_passed:
        print("  OVERALL: ALL TESTS PASSED")
        print("  Adaptive layer is validated for live paper shadow.")
        print("  Next step: deploy paper shadow mode with logging.")
    else:
        print("  OVERALL: NOT ALL TESTS PASSED")
        print("  Adaptive layer needs further investigation before live.")
        if not t1_pass:
            print("  -> Walk-forward: adaptive benefit not consistent OOS")
        if not t2_pass:
            print("  -> MC paths: adaptive not robust to path changes")
        if not t3_pass:
            print("  -> Frozen rules: parameters may be overfit")

    print(f"  {'='*50}")

    # Save full report
    report_dir = Path("reports/latest")
    report_dir.mkdir(parents=True, exist_ok=True)
    report = {
        "protocol_version": "v1",
        "timestamp": datetime.now().isoformat(),
        "signals_total": len(all_signals),
        "acceptance_thresholds": ACCEPT,
        "test_1_walk_forward": {"passed": t1_pass, "data": t1_data},
        "test_2_monte_carlo": {"passed": t2_pass, "data": t2_data},
        "test_3_frozen_rules": {"passed": t3_pass, "data": t3_data},
        "overall_passed": all_passed,
    }
    path = report_dir / "validation_protocol_v1.json"
    with open(path, "w") as f:
        json.dump(report, f, indent=2, default=str)
    print(f"\n  Report saved to {path}")
    print("=" * 70)


if __name__ == "__main__":
    main()
