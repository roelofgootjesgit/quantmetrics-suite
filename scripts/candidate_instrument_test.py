"""
Candidate Instrument Test — Fetch data and run kernel on new markets.

Tests the SQE kernel on: US30, SPX500, NAS100, GER40, UK100, JP225
Uses the same logic as cross_instrument_runner.py but for CANDIDATE instruments.

For each instrument: fetch 5yr 15m data from Dukascopy, run full kernel,
generate scorecard, apply promotion rubric.

Usage:
    python scripts/candidate_instrument_test.py
    python scripts/candidate_instrument_test.py --skip-fetch
    python scripts/candidate_instrument_test.py --symbols US30 NAS100
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
from src.quantbuild.io.parquet_loader import (
    load_parquet, save_parquet, _fetch_dukascopy, _get_dukascopy_instrument,
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

CANDIDATE_SYMBOLS = ["US30", "SPX500", "NAS100", "GER40", "UK100", "JP225"]


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


# ── Data Fetch ───────────────────────────────────────────────────────

def fetch_instrument_data(symbol, base_path, start, end):
    """Fetch 15m and 1h data for a symbol."""
    for tf in ["15m", "1h"]:
        existing = load_parquet(base_path, symbol, tf, start=start, end=end)
        if not existing.empty and len(existing) > 1000:
            print(f"    {symbol} {tf}: {len(existing)} bars (cached)")
            continue

        print(f"    Fetching {symbol} {tf} from Dukascopy...")
        inst = _get_dukascopy_instrument(symbol)
        if inst is None:
            print(f"    WARNING: {symbol} not in Dukascopy mapping, skipping")
            return False

        try:
            data = _fetch_dukascopy(symbol, tf, start, end)
            if data.empty:
                print(f"    WARNING: No data returned for {symbol} {tf}")
                return False
            save_parquet(base_path, symbol, tf, data)
            print(f"    {symbol} {tf}: {len(data)} bars fetched")
        except Exception as e:
            print(f"    ERROR fetching {symbol} {tf}: {e}")
            return False
    return True


# ── Kernel Run ───────────────────────────────────────────────────────

def run_kernel(symbol, cfg, inst_profile, base_path, start, end):
    """Run full SQE kernel on an instrument. Returns signal list."""
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
    session_mode = inst_profile.get("session_mode", "extended")

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

            baseline_pnl = exit_baseline(exc)
            dynamic_pnl = exit_dynamic(exc, is_exp_ny)
            mfe = max((f for f, _ in exc), default=0) if exc else 0
            mae = max((a for _, a in exc), default=0) if exc else 0

            signals.append({
                "ts": ts, "symbol": symbol, "direction": direction,
                "regime": regime, "session": session,
                "pnl_baseline": baseline_pnl, "pnl_dynamic": dynamic_pnl,
                "mfe": mfe, "mae": mae,
            })

    return signals


# ── Scorecard ────────────────────────────────────────────────────────

def compute_scorecard(symbol, signals, inst_profile):
    if not signals:
        return {"symbol": symbol, "trades": 0, "status": "NO_DATA"}

    pnl_b = np.array([s["pnl_baseline"] for s in signals])
    pnl_d = np.array([s["pnl_dynamic"] for s in signals])
    mfes = np.array([s["mfe"] for s in signals])
    maes = np.array([s["mae"] for s in signals])

    def _metrics(pnl):
        wins = pnl[pnl > 0]
        losses = pnl[pnl < 0]
        gw = wins.sum() if len(wins) else 0
        gl = abs(losses.sum()) if len(losses) else 0.001
        eq = np.cumsum(pnl)
        peak = np.maximum.accumulate(eq)
        dd = eq - peak
        return {
            "trades": len(pnl),
            "wr": float(100 * len(wins) / len(pnl)),
            "pf": float(gw / gl),
            "exp": float(pnl.mean()),
            "total_r": float(pnl.sum()),
            "max_dd": float(dd.min()),
            "rdd": float(eq[-1] / abs(dd.min())) if dd.min() < 0 else 0,
        }

    base = _metrics(pnl_b)
    dyn = _metrics(pnl_d)

    # Regime split
    regime_split = {}
    for r in ["trend", "expansion"]:
        r_sigs = [s for s in signals if s["regime"] == r]
        if r_sigs:
            r_pnl = np.array([s["pnl_dynamic"] for s in r_sigs])
            r_wins = r_pnl[r_pnl > 0]
            r_losses = r_pnl[r_pnl < 0]
            regime_split[r] = {
                "trades": len(r_sigs),
                "wr": float(100 * len(r_wins) / len(r_pnl)),
                "exp": float(r_pnl.mean()),
                "total_r": float(r_pnl.sum()),
            }

    # Session split
    session_split = {}
    for s in signals:
        sess = s["session"]
        session_split.setdefault(sess, [])
        session_split[sess].append(s["pnl_dynamic"])
    session_summary = {
        k: {"trades": len(v), "exp": float(np.mean(v)), "total_r": float(np.sum(v))}
        for k, v in session_split.items()
    }

    return {
        "symbol": symbol,
        "label": inst_profile.get("label", ""),
        "asset_class": inst_profile.get("asset_class", ""),
        "baseline": base,
        "dynamic": dyn,
        "dynamic_improvement": round(dyn["total_r"] - base["total_r"], 2),
        "median_mfe": float(np.median(mfes)),
        "median_mae": float(np.median(maes)),
        "regime_split": regime_split,
        "session_split": session_summary,
    }


def apply_rubric(scorecard, thresholds):
    """Apply promotion rubric to a scorecard."""
    d = scorecard.get("dynamic", {})
    if d.get("trades", 0) < 10:
        return "INSUFFICIENT_DATA"

    promote = thresholds.get("promote", {})
    if (d.get("exp", 0) >= promote.get("min_expectancy_r", 0.15)
        and d.get("pf", 0) >= promote.get("min_profit_factor", 1.2)
        and d.get("trades", 0) >= promote.get("min_trades", 50)
        and d.get("rdd", 0) >= promote.get("min_rdd", 1.0)):
        return "PROMOTE"

    wl = thresholds.get("watchlist", {})
    if (d.get("exp", 0) >= wl.get("min_expectancy_r", 0.05)
        and d.get("pf", 0) >= wl.get("min_profit_factor", 1.0)
        and d.get("trades", 0) >= wl.get("min_trades", 30)):
        return "WATCHLIST"

    return "REJECT"


# ── Main ─────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-fetch", action="store_true")
    parser.add_argument("--symbols", nargs="+", default=CANDIDATE_SYMBOLS)
    args = parser.parse_args()

    print("=" * 70)
    print("  CANDIDATE INSTRUMENT TEST")
    print("  Testing SQE kernel on new markets")
    print("=" * 70)

    cfg = load_config(CONFIG_PATH)
    setup_logging(cfg)

    with open(PROFILES_PATH) as f:
        profiles = yaml.safe_load(f)

    instruments_cfg = profiles["instruments"]
    promotion_thresholds = profiles.get("promotion", {})
    base_path = Path(cfg.get("data", {}).get("base_path", "data/market_cache"))

    end = datetime.now()
    start = end - timedelta(days=PERIOD_DAYS)

    symbols_to_test = [s for s in args.symbols if s in instruments_cfg]
    print(f"\n  Testing: {', '.join(symbols_to_test)}")
    print(f"  Period: {start.strftime('%Y-%m-%d')} to {end.strftime('%Y-%m-%d')}")

    # Fetch data
    if not args.skip_fetch:
        print(f"\n  Fetching data...")
        for sym in symbols_to_test:
            fetch_instrument_data(sym, base_path, start, end)

    # Run kernel on each
    print(f"\n  Running kernel...")
    scorecards = []
    for sym in symbols_to_test:
        inst = instruments_cfg.get(sym, {})
        print(f"\n  --- {sym} ({inst.get('label', '')}) ---")

        signals = run_kernel(sym, cfg, inst, base_path, start, end)
        card = compute_scorecard(sym, signals, inst)
        verdict = apply_rubric(card, promotion_thresholds)
        card["verdict"] = verdict
        scorecards.append(card)

        d = card.get("dynamic", {})
        b = card.get("baseline", {})
        print(f"    Trades:        {d.get('trades', 0)}")
        print(f"    Baseline:      WR {b.get('wr', 0):.0f}%  PF {b.get('pf', 0):.2f}  "
              f"Exp {b.get('exp', 0):+.3f}R  Total {b.get('total_r', 0):+.1f}R")
        print(f"    Dynamic:       WR {d.get('wr', 0):.0f}%  PF {d.get('pf', 0):.2f}  "
              f"Exp {d.get('exp', 0):+.3f}R  Total {d.get('total_r', 0):+.1f}R")
        print(f"    Dynamic delta: {card.get('dynamic_improvement', 0):+.1f}R")
        print(f"    MFE median:    {card.get('median_mfe', 0):.1f}R")
        print(f"    MAE median:    {card.get('median_mae', 0):.1f}R")
        print(f"    Max DD:        {d.get('max_dd', 0):.1f}R")
        print(f"    R/DD:          {d.get('rdd', 0):.2f}")

        if card.get("regime_split"):
            print(f"    Regime split:")
            for reg, rs in card["regime_split"].items():
                print(f"      {reg:>12s}: {rs['trades']} trades  exp {rs['exp']:+.3f}R  total {rs['total_r']:+.1f}R")

        print(f"    >>> VERDICT: {verdict}")

    # Summary
    print("\n" + "=" * 70)
    print("  SUMMARY")
    print("=" * 70)

    header = f"  {'Symbol':<10s} {'Label':<15s} {'Trades':>6s} {'WR':>5s} {'PF':>5s} {'Exp':>7s} {'Total':>7s} {'DD':>6s} {'R/DD':>5s} {'Verdict':<12s}"
    print(header)
    print("  " + "-" * (len(header) - 2))
    for card in scorecards:
        d = card.get("dynamic", {})
        print(f"  {card['symbol']:<10s} {card.get('label', ''):<15s} "
              f"{d.get('trades', 0):>6d} {d.get('wr', 0):>4.0f}% {d.get('pf', 0):>5.2f} "
              f"{d.get('exp', 0):>+6.3f} {d.get('total_r', 0):>+6.1f} "
              f"{d.get('max_dd', 0):>+5.1f} {d.get('rdd', 0):>5.2f} {card.get('verdict', ''):>12s}")

    # Combined portfolio potential
    promoted_new = [c for c in scorecards if c["verdict"] == "PROMOTE"]
    if promoted_new:
        total_trades = sum(c["dynamic"]["trades"] for c in promoted_new)
        total_r = sum(c["dynamic"]["total_r"] for c in promoted_new)
        print(f"\n  New PROMOTED instruments: {', '.join(c['symbol'] for c in promoted_new)}")
        print(f"  Combined: {total_trades} trades, {total_r:+.1f}R over 5 years")
        print(f"  Added trade frequency: +{total_trades / 5:.0f} trades/year")

    # Save report
    report_dir = Path("reports/latest")
    report_dir.mkdir(parents=True, exist_ok=True)
    report = {
        "timestamp": datetime.now().isoformat(),
        "candidates_tested": symbols_to_test,
        "scorecards": [{k: v for k, v in c.items()} for c in scorecards],
    }
    path = report_dir / "candidate_instrument_test.json"
    with open(path, "w") as f:
        json.dump(report, f, indent=2, default=str)
    print(f"\n  Report saved to {path}")
    print("=" * 70)


if __name__ == "__main__":
    main()
