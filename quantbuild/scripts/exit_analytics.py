"""
Exit Analytics & Variant Testing for STRICT_PROD_V2.

Analyzes exit efficiency and simulates 4 exit variants:
  A) Baseline: full TP at 2R, SL 1R
  B) Partial + Breakeven: 50% off at 1R, rest to breakeven, runner to 3R
  C) Partial + ATR trail: 50% off at 1R, rest trails under ATR
  D) Expansion runner: no fixed 2R cap, trail after 1.5R (expansion NY only)

Outputs:
  - MAE/MFE distribution per regime
  - Losers that reached +0.5R / +1R first
  - Winners that exceeded +2R / +3R / +4R
  - Hold time distribution
  - Side-by-side exit variant comparison

Usage:
    python scripts/exit_analytics.py
"""
import copy
import json
import sys
from collections import defaultdict
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


def _simulate_full_excursion(cache, i, direction, atr):
    """Track full bar-by-bar price excursion in R-multiples from entry."""
    close_arr = cache["close"]
    high_arr = cache["high"]
    low_arr = cache["low"]
    ts_arr = cache["ts"]
    n = len(close_arr)

    entry_price = float(close_arr[i])
    risk = atr if atr > 0 else entry_price * 0.005

    excursion = []
    for j in range(i + 1, min(i + 200, n)):
        if direction == "LONG":
            fav = (high_arr[j] - entry_price) / risk
            adv = (entry_price - low_arr[j]) / risk
        else:
            fav = (entry_price - low_arr[j]) / risk
            adv = (high_arr[j] - entry_price) / risk
        excursion.append({
            "bar": j - i,
            "ts": ts_arr[j],
            "fav_r": float(fav),
            "adv_r": float(adv),
        })
    return excursion


def _simulate_exit_variant_a(excursion, tp_r=2.0, sl_r=1.0):
    """Variant A: baseline fixed TP/SL."""
    for bar in excursion:
        if bar["adv_r"] >= sl_r:
            return {"result": "LOSS", "profit_r": -sl_r, "bars": bar["bar"]}
        if bar["fav_r"] >= tp_r:
            return {"result": "WIN", "profit_r": tp_r, "bars": bar["bar"]}
    return {"result": "TIMEOUT", "profit_r": 0.0, "bars": len(excursion)}


def _simulate_exit_variant_b(excursion, tp_r=3.0, sl_r=1.0, partial_at=1.0):
    """Variant B: 50% off at partial_at R, rest to breakeven, runner to tp_r."""
    partial_filled = False
    for bar in excursion:
        if not partial_filled:
            if bar["adv_r"] >= sl_r:
                return {"result": "LOSS", "profit_r": -sl_r, "bars": bar["bar"]}
            if bar["fav_r"] >= partial_at:
                partial_filled = True
                continue
        else:
            # After partial: SL at breakeven (0R), TP at tp_r
            if bar["adv_r"] >= 0 and bar["fav_r"] < partial_at:
                # Price came back to entry -> breakeven on runner
                return {"result": "BE", "profit_r": partial_at * 0.5, "bars": bar["bar"]}
            if bar["fav_r"] >= tp_r:
                # Runner hit TP
                return {"result": "WIN", "profit_r": partial_at * 0.5 + tp_r * 0.5, "bars": bar["bar"]}
    if partial_filled:
        return {"result": "TIMEOUT_P", "profit_r": partial_at * 0.5, "bars": len(excursion)}
    return {"result": "TIMEOUT", "profit_r": 0.0, "bars": len(excursion)}


def _simulate_exit_variant_c(excursion, sl_r=1.0, partial_at=1.0, trail_r=1.5):
    """Variant C: 50% off at 1R, rest trails with trail_r distance from peak."""
    partial_filled = False
    peak_fav = 0.0
    for bar in excursion:
        if not partial_filled:
            if bar["adv_r"] >= sl_r:
                return {"result": "LOSS", "profit_r": -sl_r, "bars": bar["bar"]}
            if bar["fav_r"] >= partial_at:
                partial_filled = True
                peak_fav = bar["fav_r"]
                continue
        else:
            peak_fav = max(peak_fav, bar["fav_r"])
            # Trail: if price drops trail_r from peak
            drawback_from_peak = peak_fav - bar["fav_r"]
            if drawback_from_peak >= trail_r or bar["adv_r"] >= 0:
                trail_exit = max(0, peak_fav - trail_r)
                return {"result": "TRAIL", "profit_r": partial_at * 0.5 + trail_exit * 0.5,
                        "bars": bar["bar"], "peak_r": peak_fav}
    if partial_filled:
        trail_exit = max(0, peak_fav - trail_r)
        return {"result": "TIMEOUT_T", "profit_r": partial_at * 0.5 + trail_exit * 0.5,
                "bars": len(excursion), "peak_r": peak_fav}
    return {"result": "TIMEOUT", "profit_r": 0.0, "bars": len(excursion)}


def _simulate_exit_variant_d(excursion, sl_r=1.0, trail_start=1.5, trail_distance=1.0):
    """Variant D: expansion runner. No fixed cap, trail kicks in after trail_start R."""
    peak_fav = 0.0
    trailing = False
    for bar in excursion:
        if bar["adv_r"] >= sl_r:
            return {"result": "LOSS", "profit_r": -sl_r, "bars": bar["bar"]}

        peak_fav = max(peak_fav, bar["fav_r"])

        if not trailing and peak_fav >= trail_start:
            trailing = True

        if trailing:
            drawback = peak_fav - bar["fav_r"]
            if drawback >= trail_distance:
                exit_r = max(0, peak_fav - trail_distance)
                return {"result": "TRAIL", "profit_r": exit_r,
                        "bars": bar["bar"], "peak_r": peak_fav}

    if trailing:
        exit_r = max(0, peak_fav - trail_distance)
        return {"result": "TIMEOUT_T", "profit_r": exit_r,
                "bars": len(excursion), "peak_r": peak_fav}
    return {"result": "TIMEOUT", "profit_r": 0.0, "bars": len(excursion)}


def _metrics_summary(results):
    if not results:
        return {"n": 0, "total_r": 0, "wr": 0, "exp": 0, "pf": 0, "max_dd": 0}
    wins = [r for r in results if r["profit_r"] > 0]
    losses = [r for r in results if r["profit_r"] < 0]
    total_r = sum(r["profit_r"] for r in results)
    gw = sum(r["profit_r"] for r in wins) if wins else 0
    gl = abs(sum(r["profit_r"] for r in losses)) if losses else 0
    pf = (gw / gl) if gl else (gw or 0)
    wr = 100 * len(wins) / len(results) if results else 0

    equity = []
    cum = 0.0
    for r in results:
        cum += r["profit_r"]
        equity.append(cum)
    peak = equity[0] if equity else 0
    max_dd = 0
    for v in equity:
        if v > peak:
            peak = v
        dd = peak - v
        if dd > max_dd:
            max_dd = dd

    return {
        "n": len(results), "total_r": total_r,
        "wr": wr, "exp": total_r / len(results),
        "pf": pf, "max_dd": -max_dd,
        "avg_r": np.mean([r["profit_r"] for r in results]),
    }


def run_exit_analysis():
    print("=" * 70)
    print("  EXIT ANALYTICS & VARIANT TESTING -- STRICT_PROD_V2")
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

    # Regime detection
    detector = RegimeDetector(config=cfg.get("regime", {}))
    regime_series = detector.classify(data, data_1h if not data_1h.empty else None)

    # Entry signals
    sqe_cfg = get_sqe_default_config()
    strategy_cfg = cfg.get("strategy", {}) or {}
    if strategy_cfg:
        _deep_merge(sqe_cfg, strategy_cfg)

    precomputed_df = _compute_modules_once(data, sqe_cfg)
    long_entries = run_sqe_conditions(data, "LONG", sqe_cfg, _precomputed_df=precomputed_df)
    short_entries = run_sqe_conditions(data, "SHORT", sqe_cfg, _precomputed_df=precomputed_df)

    if strategy_cfg.get("structure_use_h1_gate", False) and not data_1h.empty:
        long_entries = _apply_h1_gate(long_entries, data, "LONG", base_path, symbol, start, end, sqe_cfg)
        short_entries = _apply_h1_gate(short_entries, data, "SHORT", base_path, symbol, start, end, sqe_cfg)

    sim_cache = _prepare_sim_cache(data)
    atr_arr = sim_cache["atr"]

    # Build signal list with regime + session
    signals = []
    for i in range(1, len(data) - 1):
        for direction, mask in [("LONG", long_entries), ("SHORT", short_entries)]:
            if not mask.iloc[i]:
                continue
            entry_ts = data.index[i]
            regime = regime_series.iloc[i] if i < len(regime_series) else None
            session = session_from_timestamp(entry_ts, mode=session_mode)
            atr = float(atr_arr[i])
            signals.append({
                "i": i, "direction": direction, "entry_ts": entry_ts,
                "regime": regime, "session": session, "atr": atr,
                "hour": entry_ts.hour, "year": entry_ts.year,
            })

    # Filter: apply v2 rules (skip compression, expansion only NY/Overlap >=10h)
    regime_profiles = cfg.get("regime_profiles", {})
    filtered_signals = []
    for s in signals:
        rp = regime_profiles.get(s["regime"], {}) if s["regime"] else {}
        if rp.get("skip", False):
            continue
        allowed = rp.get("allowed_sessions")
        if allowed and s["session"] not in allowed:
            continue
        min_h = rp.get("min_hour_utc")
        if min_h is not None and s["hour"] < min_h:
            continue
        filtered_signals.append(s)

    print(f"  Total signals: {len(signals)} -> After v2 filter: {len(filtered_signals)}")

    # Compute full excursion for each filtered signal
    print("\n  Computing excursions...")
    for s in filtered_signals:
        s["excursion"] = _simulate_full_excursion(sim_cache, s["i"], s["direction"], s["atr"])

    # =========================================================
    # SECTION 1: MFE/MAE DISTRIBUTION
    # =========================================================
    print("\n" + "=" * 70)
    print("  SECTION 1: MFE/MAE DISTRIBUTION (2R TP baseline)")
    print("=" * 70)

    for regime_name in [REGIME_TREND, REGIME_EXPANSION]:
        sigs = [s for s in filtered_signals if s["regime"] == regime_name]
        if not sigs:
            continue

        baseline_results = [_simulate_exit_variant_a(s["excursion"]) for s in sigs]
        losers = [s for s, r in zip(sigs, baseline_results) if r["result"] == "LOSS"]
        winners = [s for s, r in zip(sigs, baseline_results) if r["result"] == "WIN"]

        print(f"\n  {regime_name.upper()} ({len(sigs)} trades, {len(winners)}W / {len(losers)}L)")

        # Losers that reached +0.5R / +1R before stopping out
        loser_peak_mfe = [max(b["fav_r"] for b in s["excursion"][:50]) if s["excursion"] else 0 for s in losers]
        reached_05 = sum(1 for m in loser_peak_mfe if m >= 0.5)
        reached_10 = sum(1 for m in loser_peak_mfe if m >= 1.0)
        reached_15 = sum(1 for m in loser_peak_mfe if m >= 1.5)
        print(f"    Losers that reached +0.5R first: {reached_05}/{len(losers)} ({100*reached_05/len(losers):.0f}%)" if losers else "")
        print(f"    Losers that reached +1.0R first: {reached_10}/{len(losers)} ({100*reached_10/len(losers):.0f}%)" if losers else "")
        print(f"    Losers that reached +1.5R first: {reached_15}/{len(losers)} ({100*reached_15/len(losers):.0f}%)" if losers else "")

        # Winners that exceeded +2R / +3R / +4R
        winner_peak_mfe = [max(b["fav_r"] for b in s["excursion"][:200]) if s["excursion"] else 0 for s in winners]
        exceeded_3 = sum(1 for m in winner_peak_mfe if m >= 3.0)
        exceeded_4 = sum(1 for m in winner_peak_mfe if m >= 4.0)
        exceeded_5 = sum(1 for m in winner_peak_mfe if m >= 5.0)
        print(f"    Winners that exceeded +3R: {exceeded_3}/{len(winners)} ({100*exceeded_3/len(winners):.0f}%)" if winners else "")
        print(f"    Winners that exceeded +4R: {exceeded_4}/{len(winners)} ({100*exceeded_4/len(winners):.0f}%)" if winners else "")
        print(f"    Winners that exceeded +5R: {exceeded_5}/{len(winners)} ({100*exceeded_5/len(winners):.0f}%)" if winners else "")

        if loser_peak_mfe:
            print(f"    Avg loser peak MFE: {np.mean(loser_peak_mfe):.2f}R")
        if winner_peak_mfe:
            print(f"    Avg winner peak MFE: {np.mean(winner_peak_mfe):.2f}R")

    # =========================================================
    # SECTION 2: EXIT VARIANT COMPARISON
    # =========================================================
    print("\n" + "=" * 70)
    print("  SECTION 2: EXIT VARIANT COMPARISON")
    print("=" * 70)

    for regime_name in [REGIME_TREND, REGIME_EXPANSION, "ALL"]:
        if regime_name == "ALL":
            sigs = filtered_signals
        else:
            sigs = [s for s in filtered_signals if s["regime"] == regime_name]

        if not sigs:
            continue

        variant_results = {
            "A_baseline": [_simulate_exit_variant_a(s["excursion"]) for s in sigs],
            "B_partial_BE": [_simulate_exit_variant_b(s["excursion"]) for s in sigs],
            "C_partial_trail": [_simulate_exit_variant_c(s["excursion"]) for s in sigs],
            "D_runner": [_simulate_exit_variant_d(s["excursion"]) for s in sigs],
        }

        print(f"\n  --- {regime_name.upper()} ({len(sigs)} trades) ---")
        header = f"  {'Variant':<18s} {'N':>5s} {'WR':>6s} {'PF':>6s} {'Exp':>7s} {'Total R':>9s} {'Max DD':>8s}"
        print(header)
        print("  " + "-" * (len(header) - 2))

        for name, results in variant_results.items():
            m = _metrics_summary(results)
            print(f"  {name:<18s} {m['n']:>5d} {m['wr']:>5.1f}% {m['pf']:>6.2f} "
                  f"{m['exp']:>+6.3f}R {m['total_r']:>+8.1f}R {m['max_dd']:>+7.1f}R")

    # =========================================================
    # SECTION 3: EXPANSION NY EXIT DEEP DIVE
    # =========================================================
    print("\n" + "=" * 70)
    print("  SECTION 3: EXPANSION NY/OVERLAP EXIT DEEP DIVE")
    print("=" * 70)

    exp_ny = [s for s in filtered_signals
              if s["regime"] == REGIME_EXPANSION
              and s["session"] in ("New York", "Overlap")
              and s["hour"] >= 10]

    if exp_ny:
        print(f"\n  Expansion NY/Overlap >=10:00 UTC: {len(exp_ny)} trades")

        variant_results = {
            "A_baseline_2R": [_simulate_exit_variant_a(s["excursion"], tp_r=2.0) for s in exp_ny],
            "A_baseline_3R": [_simulate_exit_variant_a(s["excursion"], tp_r=3.0) for s in exp_ny],
            "B_partial_3R": [_simulate_exit_variant_b(s["excursion"], tp_r=3.0) for s in exp_ny],
            "C_partial_trail": [_simulate_exit_variant_c(s["excursion"], trail_r=1.0) for s in exp_ny],
            "D_runner_1.5": [_simulate_exit_variant_d(s["excursion"], trail_start=1.5, trail_distance=1.0) for s in exp_ny],
            "D_runner_2.0": [_simulate_exit_variant_d(s["excursion"], trail_start=2.0, trail_distance=1.0) for s in exp_ny],
        }

        header = f"  {'Variant':<18s} {'N':>5s} {'WR':>6s} {'PF':>6s} {'Exp':>7s} {'Total R':>9s} {'Max DD':>8s}"
        print(header)
        print("  " + "-" * (len(header) - 2))

        for name, results in variant_results.items():
            m = _metrics_summary(results)
            print(f"  {name:<18s} {m['n']:>5d} {m['wr']:>5.1f}% {m['pf']:>6.2f} "
                  f"{m['exp']:>+6.3f}R {m['total_r']:>+8.1f}R {m['max_dd']:>+7.1f}R")

    # =========================================================
    # SECTION 4: YEARLY EXIT VARIANT BREAKDOWN
    # =========================================================
    print("\n" + "=" * 70)
    print("  SECTION 4: YEARLY COMPARISON (ALL filtered signals)")
    print("=" * 70)

    years = sorted(set(s["year"] for s in filtered_signals))

    for variant_name, variant_fn in [
        ("A_baseline", lambda exc: _simulate_exit_variant_a(exc)),
        ("B_partial_BE", lambda exc: _simulate_exit_variant_b(exc)),
        ("C_partial_trail", lambda exc: _simulate_exit_variant_c(exc)),
    ]:
        print(f"\n  {variant_name}:")
        for year in years:
            yr_sigs = [s for s in filtered_signals if s["year"] == year]
            results = [variant_fn(s["excursion"]) for s in yr_sigs]
            m = _metrics_summary(results)
            print(f"    {year}: {m['n']:>3d} trades, WR {m['wr']:>5.1f}%, "
                  f"PF {m['pf']:.2f}, {m['total_r']:>+7.1f}R, DD {m['max_dd']:>+6.1f}R")

    # Save
    report_dir = Path("reports/latest")
    report_dir.mkdir(parents=True, exist_ok=True)
    path = report_dir / "exit_analytics.json"

    all_baseline = [_simulate_exit_variant_a(s["excursion"]) for s in filtered_signals]
    all_partial = [_simulate_exit_variant_b(s["excursion"]) for s in filtered_signals]
    all_trail = [_simulate_exit_variant_c(s["excursion"]) for s in filtered_signals]

    summary = {
        "config": "STRICT_PROD_V2",
        "total_filtered_signals": len(filtered_signals),
        "A_baseline": _metrics_summary(all_baseline),
        "B_partial_BE": _metrics_summary(all_partial),
        "C_partial_trail": _metrics_summary(all_trail),
    }
    with open(path, "w") as f:
        json.dump(summary, f, indent=2, default=str)

    print(f"\n  Results saved to {path}")
    print("=" * 70)


if __name__ == "__main__":
    run_exit_analysis()
