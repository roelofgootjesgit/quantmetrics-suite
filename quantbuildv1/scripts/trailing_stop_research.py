"""
Trailing Stop Research: MFE distribution + structure trailing stop.

Tests 5 exit strategies head-to-head:
  1. Baseline: fixed 2R TP
  2. Fixed trail: BE at 1R, trail 1.5R distance
  3. ATR trail: BE at 1R, trail 2*ATR from peak
  4. Structure trail: BE at 1R, trail to last swing low/high
  5. Hybrid 3-phase: BE at 1R, 40% partial at 2R, structure trail for runner

Usage:
    python scripts/trailing_stop_research.py
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


# ── Raw excursion with actual prices ──────────────────────────────────

def _raw_excursion(cache, i, direction, max_bars=200):
    """Return bar-by-bar high/low/close + ATR in actual price, plus R-multiples."""
    close_arr, high_arr, low_arr, atr_arr, ts_arr = (
        cache["close"], cache["high"], cache["low"], cache["atr"], cache["ts"]
    )
    n = len(close_arr)
    entry = float(close_arr[i])
    atr_entry = float(atr_arr[i])
    risk = atr_entry if atr_entry > 0 else entry * 0.005

    bars = []
    for j in range(i + 1, min(i + max_bars, n)):
        hi, lo, cl = float(high_arr[j]), float(low_arr[j]), float(close_arr[j])
        atr_j = float(atr_arr[j])
        if direction == "LONG":
            fav_r = (hi - entry) / risk
            adv_r = (entry - lo) / risk
        else:
            fav_r = (entry - lo) / risk
            adv_r = (hi - entry) / risk
        bars.append({
            "hi": hi, "lo": lo, "cl": cl,
            "atr": atr_j, "fav_r": fav_r, "adv_r": adv_r,
        })
    return bars, entry, risk, atr_entry


# ── Swing detection ───────────────────────────────────────────────────

def _find_swing_lows(bars, pivot_n=2):
    """Find swing lows: bar where low < low of surrounding pivot_n bars."""
    lows = [b["lo"] for b in bars]
    swings = []
    for j in range(pivot_n, len(lows) - pivot_n):
        is_swing = True
        for k in range(1, pivot_n + 1):
            if lows[j] >= lows[j - k] or lows[j] >= lows[j + k]:
                is_swing = False
                break
        if is_swing:
            swings.append((j, lows[j]))
    return swings


def _find_swing_highs(bars, pivot_n=2):
    """Find swing highs: bar where high > high of surrounding pivot_n bars."""
    highs = [b["hi"] for b in bars]
    swings = []
    for j in range(pivot_n, len(highs) - pivot_n):
        is_swing = True
        for k in range(1, pivot_n + 1):
            if highs[j] <= highs[j - k] or highs[j] <= highs[j + k]:
                is_swing = False
                break
        if is_swing:
            swings.append((j, highs[j]))
    return swings


# ── Exit strategies ───────────────────────────────────────────────────

def exit_baseline(bars, sl_r=1.0, tp_r=2.0):
    for b in bars:
        if b["adv_r"] >= sl_r:
            return -sl_r
        if b["fav_r"] >= tp_r:
            return tp_r
    return 0.0


def exit_fixed_trail(bars, sl_r=1.0, be_at=1.0, trail_dist=1.5):
    """BE at be_at R, then trail with fixed R distance from peak."""
    be_moved = False
    peak_fav = 0.0
    for b in bars:
        if not be_moved:
            if b["adv_r"] >= sl_r:
                return -sl_r
            if b["fav_r"] >= be_at:
                be_moved = True
                peak_fav = b["fav_r"]
                continue
        else:
            peak_fav = max(peak_fav, b["fav_r"])
            trail_level = peak_fav - trail_dist
            current_r = b["fav_r"]
            if current_r <= trail_level or b["adv_r"] >= 0:
                return max(0, trail_level)
    if be_moved:
        return max(0, peak_fav - trail_dist)
    return 0.0


def exit_atr_trail(bars, entry, risk, direction, sl_r=1.0, be_at=1.0, atr_mult=2.0):
    """BE at be_at R, then trail at atr_mult * current ATR from peak close."""
    be_moved = False
    peak_close = entry
    for b in bars:
        if not be_moved:
            if b["adv_r"] >= sl_r:
                return -sl_r
            if b["fav_r"] >= be_at:
                be_moved = True
                peak_close = b["cl"]
                continue
        else:
            if direction == "LONG":
                peak_close = max(peak_close, b["cl"])
                trail_price = peak_close - atr_mult * b["atr"]
                if b["lo"] <= trail_price:
                    exit_r = (trail_price - entry) / risk
                    return max(0, exit_r)
            else:
                peak_close = min(peak_close, b["cl"])
                trail_price = peak_close + atr_mult * b["atr"]
                if b["hi"] >= trail_price:
                    exit_r = (entry - trail_price) / risk
                    return max(0, exit_r)
    if be_moved:
        if direction == "LONG":
            return max(0, (peak_close - atr_mult * bars[-1]["atr"] - entry) / risk)
        else:
            return max(0, (entry - peak_close - atr_mult * bars[-1]["atr"]) / risk)
    return 0.0


def exit_structure_trail(bars, entry, risk, direction, sl_r=1.0, be_at=1.0, pivot_n=2):
    """BE at be_at R, then trail to last swing low (long) or swing high (short)."""
    be_moved = False

    if direction == "LONG":
        swings = _find_swing_lows(bars, pivot_n)
    else:
        swings = _find_swing_highs(bars, pivot_n)

    swing_idx = 0
    current_trail_price = None

    for j, b in enumerate(bars):
        if not be_moved:
            if b["adv_r"] >= sl_r:
                return -sl_r
            if b["fav_r"] >= be_at:
                be_moved = True
                current_trail_price = entry
                continue
        else:
            # Update trail to latest confirmed swing
            while swing_idx < len(swings) and swings[swing_idx][0] <= j - pivot_n:
                swing_bar_idx, swing_price = swings[swing_idx]
                if direction == "LONG" and swing_price > current_trail_price:
                    current_trail_price = swing_price
                elif direction == "SHORT" and (current_trail_price is None or swing_price < current_trail_price):
                    current_trail_price = swing_price
                swing_idx += 1

            if current_trail_price is not None:
                if direction == "LONG" and b["lo"] <= current_trail_price:
                    return max(0, (current_trail_price - entry) / risk)
                elif direction == "SHORT" and b["hi"] >= current_trail_price:
                    return max(0, (entry - current_trail_price) / risk)

    if be_moved and current_trail_price is not None:
        if direction == "LONG":
            return max(0, (current_trail_price - entry) / risk)
        else:
            return max(0, (entry - current_trail_price) / risk)
    return 0.0


def exit_hybrid_3phase(bars, entry, risk, direction, sl_r=1.0, be_at=1.0,
                       partial_at=2.0, partial_pct=0.4, pivot_n=2):
    """3-phase: BE at 1R, 40% partial at 2R, structure trail for 60% runner."""
    be_moved = False
    partial_taken = False

    if direction == "LONG":
        swings = _find_swing_lows(bars, pivot_n)
    else:
        swings = _find_swing_highs(bars, pivot_n)

    swing_idx = 0
    current_trail_price = None

    for j, b in enumerate(bars):
        if not be_moved:
            if b["adv_r"] >= sl_r:
                return -sl_r
            if b["fav_r"] >= be_at:
                be_moved = True
                current_trail_price = entry
                continue
        elif not partial_taken:
            if b["fav_r"] >= partial_at:
                partial_taken = True
                continue
            # Still at BE stop
            if b["adv_r"] >= 0 and b["fav_r"] < 0:
                return 0.0
        else:
            # Phase 3: structure trail for the runner portion
            while swing_idx < len(swings) and swings[swing_idx][0] <= j - pivot_n:
                _, swing_price = swings[swing_idx]
                if direction == "LONG" and swing_price > (current_trail_price or entry):
                    current_trail_price = swing_price
                elif direction == "SHORT" and (current_trail_price is None or swing_price < current_trail_price):
                    current_trail_price = swing_price
                swing_idx += 1

            if current_trail_price is not None:
                if direction == "LONG" and b["lo"] <= current_trail_price:
                    runner_r = max(0, (current_trail_price - entry) / risk)
                    return partial_pct * partial_at + (1 - partial_pct) * runner_r
                elif direction == "SHORT" and b["hi"] >= current_trail_price:
                    runner_r = max(0, (entry - current_trail_price) / risk)
                    return partial_pct * partial_at + (1 - partial_pct) * runner_r

    if partial_taken and current_trail_price is not None:
        if direction == "LONG":
            runner_r = max(0, (current_trail_price - entry) / risk)
        else:
            runner_r = max(0, (entry - current_trail_price) / risk)
        return partial_pct * partial_at + (1 - partial_pct) * runner_r
    if partial_taken:
        return partial_pct * partial_at
    if be_moved:
        return 0.0
    return 0.0


# ── Metrics ───────────────────────────────────────────────────────────

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
        "avg_win": float(wins.mean()) if len(wins) else 0,
        "avg_loss": float(losses.mean()) if len(losses) else 0,
    }


# ── Main ──────────────────────────────────────────────────────────────

def main():
    print("=" * 70)
    print("  TRAILING STOP RESEARCH: MFE Distribution + Structure Trail")
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
    atr_arr = sim_cache["atr"]
    regime_profiles = cfg.get("regime_profiles", {})

    # Build V2-filtered signals with raw excursion
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
            bars, entry, risk, atr_entry = _raw_excursion(sim_cache, i, direction)
            is_exp_ny = (regime == REGIME_EXPANSION and session in ("New York", "Overlap") and ts.hour >= 10)
            signals.append({
                "i": i, "direction": direction, "ts": ts,
                "regime": regime, "session": session,
                "bars": bars, "entry": entry, "risk": risk, "atr_entry": atr_entry,
                "year": ts.year, "is_exp_ny": is_exp_ny,
            })

    print(f"\n  V2-filtered signals: {len(signals)}")
    trend_sigs = [s for s in signals if s["regime"] == REGIME_TREND]
    exp_ny_sigs = [s for s in signals if s["is_exp_ny"]]
    print(f"    TREND: {len(trend_sigs)} | EXPANSION_NY: {len(exp_ny_sigs)}")

    # =========================================================
    # SECTION 1: MFE DISTRIBUTION
    # =========================================================
    print("\n" + "=" * 70)
    print("  SECTION 1: MFE DISTRIBUTION (winners only, baseline 2R TP)")
    print("=" * 70)

    for label, sigs in [("TREND", trend_sigs), ("EXPANSION_NY", exp_ny_sigs), ("ALL", signals)]:
        # Determine winners under baseline
        winner_mfes = []
        loser_mfes = []
        all_mfes = []
        for s in sigs:
            bl = exit_baseline(s["bars"])
            peak_mfe = max((b["fav_r"] for b in s["bars"]), default=0)
            all_mfes.append(peak_mfe)
            if bl > 0:
                winner_mfes.append(peak_mfe)
            elif bl < 0:
                loser_mfes.append(peak_mfe)

        if not winner_mfes:
            continue

        wm = np.array(winner_mfes)
        lm = np.array(loser_mfes)
        am = np.array(all_mfes)

        print(f"\n  {label} ({len(sigs)} signals)")
        print(f"\n    WINNER MFE (peak R before exit, {len(wm)} winners):")
        print(f"      Mean:     {wm.mean():.2f}R")
        print(f"      Median:   {np.median(wm):.2f}R")
        print(f"      25th pct: {np.percentile(wm, 25):.2f}R")
        print(f"      75th pct: {np.percentile(wm, 75):.2f}R")
        print(f"      90th pct: {np.percentile(wm, 90):.2f}R")
        print(f"      Max:      {wm.max():.2f}R")

        print(f"\n    LOSER MFE (peak R before stopping out, {len(lm)} losers):")
        print(f"      Mean:     {lm.mean():.2f}R")
        print(f"      Median:   {np.median(lm):.2f}R")
        print(f"      25th pct: {np.percentile(lm, 25):.2f}R")
        print(f"      75th pct: {np.percentile(lm, 75):.2f}R")

        # Distribution buckets
        print(f"\n    MFE DISTRIBUTION (all {len(am)} signals):")
        for threshold in [0.5, 1.0, 1.5, 2.0, 3.0, 4.0, 5.0, 7.0, 10.0]:
            count = (am >= threshold).sum()
            pct = 100 * count / len(am)
            print(f"      >= {threshold:>4.1f}R: {count:>4d} ({pct:>5.1f}%)")

    # =========================================================
    # SECTION 2: TRAILING STOP COMPARISON
    # =========================================================
    print("\n" + "=" * 70)
    print("  SECTION 2: TRAILING STOP TYPE COMPARISON")
    print("=" * 70)

    for label, sigs in [("TREND", trend_sigs), ("EXPANSION_NY", exp_ny_sigs), ("ALL", signals)]:
        if not sigs:
            continue

        results = {}

        # 1. Baseline
        results["1_baseline_2R"] = [exit_baseline(s["bars"]) for s in sigs]

        # 2. Fixed trail
        results["2_fixed_trail"] = [exit_fixed_trail(s["bars"], trail_dist=1.5) for s in sigs]

        # 3. ATR trail (2x ATR)
        results["3_atr_2x"] = [
            exit_atr_trail(s["bars"], s["entry"], s["risk"], s["direction"], atr_mult=2.0)
            for s in sigs
        ]

        # 4. ATR trail (3x ATR)
        results["4_atr_3x"] = [
            exit_atr_trail(s["bars"], s["entry"], s["risk"], s["direction"], atr_mult=3.0)
            for s in sigs
        ]

        # 5. Structure trail (2-bar pivot)
        results["5_struct_p2"] = [
            exit_structure_trail(s["bars"], s["entry"], s["risk"], s["direction"], pivot_n=2)
            for s in sigs
        ]

        # 6. Structure trail (3-bar pivot)
        results["6_struct_p3"] = [
            exit_structure_trail(s["bars"], s["entry"], s["risk"], s["direction"], pivot_n=3)
            for s in sigs
        ]

        # 7. Hybrid 3-phase (40% partial 2R + structure trail)
        results["7_hybrid_3ph"] = [
            exit_hybrid_3phase(s["bars"], s["entry"], s["risk"], s["direction"],
                               partial_at=2.0, partial_pct=0.4, pivot_n=2)
            for s in sigs
        ]

        # 8. Hybrid 3-phase (30% partial 2R + structure trail p3)
        results["8_hybrid_p3"] = [
            exit_hybrid_3phase(s["bars"], s["entry"], s["risk"], s["direction"],
                               partial_at=2.0, partial_pct=0.3, pivot_n=3)
            for s in sigs
        ]

        print(f"\n  --- {label} ({len(sigs)} trades) ---")
        header = (f"  {'Exit Type':<18s} {'N':>4s} {'WR':>6s} {'PF':>6s} "
                  f"{'Exp':>7s} {'TotalR':>8s} {'MaxDD':>7s} {'R/DD':>6s} "
                  f"{'AvgW':>6s} {'AvgL':>6s}")
        print(header)
        print("  " + "-" * (len(header) - 2))

        for name, pnl_list in results.items():
            m = compute_metrics(pnl_list)
            rdd = m["total_r"] / abs(m["max_dd"]) if m["max_dd"] else 0
            print(f"  {name:<18s} {m['n']:>4d} {m['wr']:>5.1f}% {m['pf']:>6.2f} "
                  f"{m['exp']:>+6.3f}R {m['total_r']:>+7.1f}R {m['max_dd']:>+6.1f}R "
                  f"{rdd:>5.2f} {m['avg_win']:>+5.2f} {m['avg_loss']:>+5.2f}")

    # =========================================================
    # SECTION 3: BEST COMBO — SEGMENT-SPECIFIC
    # =========================================================
    print("\n" + "=" * 70)
    print("  SECTION 3: OPTIMAL SEGMENT-SPECIFIC EXIT COMBO")
    print("=" * 70)

    # Find best for TREND and EXPANSION_NY, then combine
    best_combos = [
        ("TREND: struct_p3 | EXP_NY: struct_p3",
         lambda s: exit_structure_trail(s["bars"], s["entry"], s["risk"], s["direction"], pivot_n=3)),
        ("TREND: hybrid_3ph | EXP_NY: struct_p3",
         None),  # special
        ("TREND: hybrid_p3 | EXP_NY: struct_p2",
         None),  # special
    ]

    # Combo 1: same exit for all
    for combo_label, exit_fn in [
        ("All: baseline 2R", lambda s: exit_baseline(s["bars"])),
        ("All: struct_p2", lambda s: exit_structure_trail(s["bars"], s["entry"], s["risk"], s["direction"], pivot_n=2)),
        ("All: struct_p3", lambda s: exit_structure_trail(s["bars"], s["entry"], s["risk"], s["direction"], pivot_n=3)),
        ("All: hybrid_3ph p2", lambda s: exit_hybrid_3phase(s["bars"], s["entry"], s["risk"], s["direction"], pivot_n=2)),
        ("All: hybrid_3ph p3", lambda s: exit_hybrid_3phase(s["bars"], s["entry"], s["risk"], s["direction"], pivot_n=3)),
    ]:
        pnl = [exit_fn(s) for s in signals]
        m = compute_metrics(pnl)
        rdd = m["total_r"] / abs(m["max_dd"]) if m["max_dd"] else 0
        print(f"  {combo_label:<30s}  {m['n']:>4d} trades  WR {m['wr']:>5.1f}%  "
              f"PF {m['pf']:>5.2f}  Exp {m['exp']:>+6.3f}R  "
              f"R {m['total_r']:>+7.1f}  DD {m['max_dd']:>+6.1f}  R/DD {rdd:>5.2f}")

    # Combo 2: TREND gets hybrid, EXPANSION_NY gets structure
    for trend_exit, trend_label, exp_exit, exp_label in [
        (lambda s: exit_hybrid_3phase(s["bars"], s["entry"], s["risk"], s["direction"], pivot_n=2),
         "hybrid_p2",
         lambda s: exit_structure_trail(s["bars"], s["entry"], s["risk"], s["direction"], pivot_n=3),
         "struct_p3"),
        (lambda s: exit_hybrid_3phase(s["bars"], s["entry"], s["risk"], s["direction"], pivot_n=3),
         "hybrid_p3",
         lambda s: exit_structure_trail(s["bars"], s["entry"], s["risk"], s["direction"], pivot_n=2),
         "struct_p2"),
    ]:
        pnl = []
        for s in signals:
            if s["is_exp_ny"]:
                pnl.append(exp_exit(s))
            else:
                pnl.append(trend_exit(s))
        m = compute_metrics(pnl)
        rdd = m["total_r"] / abs(m["max_dd"]) if m["max_dd"] else 0
        combo_label = f"T:{trend_label} E:{exp_label}"
        print(f"  {combo_label:<30s}  {m['n']:>4d} trades  WR {m['wr']:>5.1f}%  "
              f"PF {m['pf']:>5.2f}  Exp {m['exp']:>+6.3f}R  "
              f"R {m['total_r']:>+7.1f}  DD {m['max_dd']:>+6.1f}  R/DD {rdd:>5.2f}")

    # =========================================================
    # SECTION 4: YEARLY BREAKDOWN — BEST COMBO
    # =========================================================
    print("\n" + "=" * 70)
    print("  SECTION 4: YEARLY — BASELINE vs STRUCTURE TRAIL vs HYBRID")
    print("=" * 70)

    exit_strategies = {
        "baseline": lambda s: exit_baseline(s["bars"]),
        "struct_p3": lambda s: exit_structure_trail(s["bars"], s["entry"], s["risk"], s["direction"], pivot_n=3),
        "hybrid_p2": lambda s: exit_hybrid_3phase(s["bars"], s["entry"], s["risk"], s["direction"], pivot_n=2),
    }

    years = sorted(set(s["year"] for s in signals))
    for name, fn in exit_strategies.items():
        print(f"\n  {name}:")
        for year in years:
            yr_sigs = [s for s in signals if s["year"] == year]
            pnl = [fn(s) for s in yr_sigs]
            m = compute_metrics(pnl)
            print(f"    {year}: {m['n']:>3d} trades, WR {m['wr']:>5.1f}%, "
                  f"PF {m['pf']:.2f}, {m['total_r']:>+7.1f}R, DD {m['max_dd']:>+6.1f}R")

    # Save
    report_dir = Path("reports/latest")
    report_dir.mkdir(parents=True, exist_ok=True)
    path = report_dir / "trailing_stop_research.json"

    save_data = {}
    for name, fn in exit_strategies.items():
        pnl = [fn(s) for s in signals]
        save_data[name] = compute_metrics(pnl)
    with open(path, "w") as f:
        json.dump(save_data, f, indent=2, default=str)

    print(f"\n  Results saved to {path}")
    print("=" * 70)


if __name__ == "__main__":
    main()
