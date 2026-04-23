"""
EURUSD Diagnostic Report — deep analysis of why EURUSD fails as trend system
and what role it can play in the portfolio.

Analyzes:
  1. Per-regime breakdown (TREND / EXPANSION / COMPRESSION)
  2. Per-session breakdown (London / NY / Overlap / Asia)
  3. Direction analysis (LONG vs SHORT)
  4. MFE/MAE distribution (is it entries or exits?)
  5. Temporal patterns (which years/months)
  6. Correlation with core instruments (regime filter potential)
  7. Role recommendation: REGIME_FILTER vs MEAN_REVERSION vs REJECT

Usage:
    python scripts/eurusd_diagnostic.py
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
from src.quantbuild.io.parquet_loader import (
    load_parquet, save_parquet, _fetch_dukascopy, _get_dukascopy_instrument,
)
from src.quantbuild.strategies.sqe_xauusd import (
    run_sqe_conditions, get_sqe_default_config, _compute_modules_once,
)
from src.quantbuild.strategy_modules.regime.detector import (
    RegimeDetector, REGIME_TREND, REGIME_EXPANSION, REGIME_COMPRESSION,
)

CONFIG_PATH = "configs/strict_prod_v2.yaml"
SYMBOL = "EURUSD"
PERIOD_DAYS = 1825


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


def main():
    print("=" * 70)
    print("  EURUSD DIAGNOSTIC REPORT")
    print("  Why does the SQE kernel fail on EURUSD?")
    print("  What role can EURUSD play in the portfolio?")
    print("=" * 70)

    cfg = load_config(CONFIG_PATH)

    base_path = Path(cfg.get("data", {}).get("base_path", "data/market_cache"))
    end = datetime.now()
    start = end - timedelta(days=PERIOD_DAYS)

    # Fetch data if needed
    for tf in ["15m", "1h"]:
        existing = load_parquet(base_path, SYMBOL, tf, start=start, end=end)
        if existing.empty or len(existing) < 1000:
            print(f"  Fetching {SYMBOL} {tf} from Dukascopy...")
            data = _fetch_dukascopy(SYMBOL, tf, start, end)
            save_parquet(base_path, SYMBOL, tf, data)
            print(f"  {len(data)} bars fetched")

    data_15m = load_parquet(base_path, SYMBOL, "15m", start=start, end=end).sort_index()
    data_1h = load_parquet(base_path, SYMBOL, "1h", start=start, end=end).sort_index()

    print(f"\n  Data: {len(data_15m)} bars (15m), {len(data_1h)} bars (1h)")
    print(f"  Period: {data_15m.index[0]} to {data_15m.index[-1]}")

    # Regime detection
    detector = RegimeDetector(config=cfg.get("regime", {}))
    regime_series = detector.classify(data_15m, data_1h if not data_1h.empty else None)

    # SQE signals
    sqe_cfg = get_sqe_default_config()
    strategy_cfg = cfg.get("strategy", {}) or {}
    if strategy_cfg:
        _deep_merge(sqe_cfg, strategy_cfg)

    precomputed_df = _compute_modules_once(data_15m, sqe_cfg)
    long_e = run_sqe_conditions(data_15m, "LONG", sqe_cfg, _precomputed_df=precomputed_df)
    short_e = run_sqe_conditions(data_15m, "SHORT", sqe_cfg, _precomputed_df=precomputed_df)

    if strategy_cfg.get("structure_use_h1_gate", False) and not data_1h.empty:
        long_e = _apply_h1_gate(long_e, data_15m, "LONG", base_path, SYMBOL, start, end, sqe_cfg)
        short_e = _apply_h1_gate(short_e, data_15m, "SHORT", base_path, SYMBOL, start, end, sqe_cfg)

    sim_cache = _prepare_sim_cache(data_15m)

    # Collect all signals
    signals = []
    for i in range(1, len(data_15m) - 1):
        for direction, mask in [("LONG", long_e), ("SHORT", short_e)]:
            if not mask.iloc[i]:
                continue
            ts = data_15m.index[i]
            regime = regime_series.iloc[i] if i < len(regime_series) else REGIME_TREND
            session = session_from_timestamp(ts, mode="extended")

            exc = _full_excursion(sim_cache, i, direction)
            pnl = exit_baseline(exc)
            mfe = max((f for f, _ in exc), default=0) if exc else 0
            mae = max((a for _, a in exc), default=0) if exc else 0

            signals.append({
                "ts": ts, "direction": direction, "regime": regime,
                "session": session, "pnl": pnl, "mfe": mfe, "mae": mae,
                "year": ts.year, "month": ts.month, "hour": ts.hour,
            })

    print(f"\n  Total signals: {len(signals)}")

    if not signals:
        print("  NO SIGNALS GENERATED — strategy too strict for EURUSD")
        print("  Recommendation: REGIME_FILTER role (no direct trading)")
        return

    pnl_arr = np.array([s["pnl"] for s in signals])
    mfe_arr = np.array([s["mfe"] for s in signals])
    mae_arr = np.array([s["mae"] for s in signals])

    wins = pnl_arr[pnl_arr > 0]
    losses = pnl_arr[pnl_arr < 0]

    print(f"\n  --- OVERALL ---")
    print(f"  Trades: {len(signals)}")
    print(f"  WR: {100 * len(wins) / len(pnl_arr):.0f}%")
    print(f"  Exp: {pnl_arr.mean():+.3f}R")
    print(f"  PF: {wins.sum() / abs(losses.sum()):.2f}" if len(losses) else "  PF: inf")
    print(f"  Total: {pnl_arr.sum():+.1f}R")
    print(f"  MFE median: {np.median(mfe_arr):.1f}R")
    print(f"  MAE median: {np.median(mae_arr):.1f}R")

    # ── 1. Per-regime breakdown ──────────────────────────────
    print(f"\n  --- PER REGIME ---")
    for reg in [REGIME_TREND, REGIME_EXPANSION, REGIME_COMPRESSION]:
        r_sigs = [s for s in signals if s["regime"] == reg]
        if not r_sigs:
            print(f"  {reg:>12s}: 0 trades")
            continue
        r_pnl = np.array([s["pnl"] for s in r_sigs])
        r_wins = r_pnl[r_pnl > 0]
        r_losses = r_pnl[r_pnl < 0]
        r_mfe = np.array([s["mfe"] for s in r_sigs])
        gw = r_wins.sum() if len(r_wins) else 0
        gl = abs(r_losses.sum()) if len(r_losses) else 0.001
        print(f"  {reg:>12s}: {len(r_sigs)} trades  WR {100*len(r_wins)/len(r_pnl):.0f}%  "
              f"exp {r_pnl.mean():+.3f}R  total {r_pnl.sum():+.1f}R  PF {gw/gl:.2f}  "
              f"MFE_med {np.median(r_mfe):.1f}R")

    # ── 2. Per-session breakdown ─────────────────────────────
    print(f"\n  --- PER SESSION ---")
    session_groups = {}
    for s in signals:
        session_groups.setdefault(s["session"], []).append(s)
    for sess in sorted(session_groups):
        sigs = session_groups[sess]
        s_pnl = np.array([s["pnl"] for s in sigs])
        s_wins = s_pnl[s_pnl > 0]
        print(f"  {sess:>12s}: {len(sigs)} trades  WR {100*len(s_wins)/len(s_pnl):.0f}%  "
              f"exp {s_pnl.mean():+.3f}R  total {s_pnl.sum():+.1f}R")

    # ── 3. Direction analysis ────────────────────────────────
    print(f"\n  --- PER DIRECTION ---")
    for d in ["LONG", "SHORT"]:
        d_sigs = [s for s in signals if s["direction"] == d]
        if not d_sigs:
            continue
        d_pnl = np.array([s["pnl"] for s in d_sigs])
        d_wins = d_pnl[d_pnl > 0]
        print(f"  {d:>12s}: {len(d_sigs)} trades  WR {100*len(d_wins)/len(d_pnl):.0f}%  "
              f"exp {d_pnl.mean():+.3f}R  total {d_pnl.sum():+.1f}R")

    # ── 4. MFE/MAE distribution ──────────────────────────────
    print(f"\n  --- MFE/MAE ANALYSIS ---")
    print(f"  All trades:")
    print(f"    MFE: mean={mfe_arr.mean():.1f}R  med={np.median(mfe_arr):.1f}R  "
          f"p25={np.percentile(mfe_arr, 25):.1f}R  p75={np.percentile(mfe_arr, 75):.1f}R")
    print(f"    MAE: mean={mae_arr.mean():.1f}R  med={np.median(mae_arr):.1f}R  "
          f"p25={np.percentile(mae_arr, 25):.1f}R  p75={np.percentile(mae_arr, 75):.1f}R")

    loser_mfe = np.array([s["mfe"] for s in signals if s["pnl"] < 0])
    if len(loser_mfe):
        pct_losers_were_profitable = 100 * (loser_mfe > 1.0).mean()
        print(f"    Losers with MFE > 1R: {pct_losers_were_profitable:.0f}%")
        print(f"    Loser median MFE: {np.median(loser_mfe):.1f}R")

    winner_mfe = np.array([s["mfe"] for s in signals if s["pnl"] > 0])
    if len(winner_mfe):
        pct_winners_beyond_2r = 100 * (winner_mfe > 3.0).mean()
        print(f"    Winners with MFE > 3R: {pct_winners_beyond_2r:.0f}%")
        print(f"    Winner median MFE: {np.median(winner_mfe):.1f}R")

    # ── 5. Temporal patterns ─────────────────────────────────
    print(f"\n  --- PER YEAR ---")
    year_groups = {}
    for s in signals:
        year_groups.setdefault(s["year"], []).append(s)
    for yr in sorted(year_groups):
        y_pnl = np.array([s["pnl"] for s in year_groups[yr]])
        print(f"  {yr}: {len(y_pnl)} trades  exp {y_pnl.mean():+.3f}R  total {y_pnl.sum():+.1f}R")

    # ── 6. Regime state correlation with XAU/NAS performance ─
    print(f"\n  --- REGIME FILTER POTENTIAL ---")
    # Count regime distribution
    for reg in [REGIME_TREND, REGIME_EXPANSION, REGIME_COMPRESSION]:
        count = (regime_series == reg).sum()
        pct = 100 * count / len(regime_series)
        print(f"  EURUSD {reg:>12s}: {pct:.1f}% of time")

    eurusd_in_compression_pct = 100 * (regime_series == REGIME_COMPRESSION).sum() / len(regime_series)
    eurusd_in_trend_pct = 100 * (regime_series == REGIME_TREND).sum() / len(regime_series)
    print(f"\n  EURUSD spends {eurusd_in_compression_pct:.0f}% in COMPRESSION")
    print(f"  EURUSD spends {eurusd_in_trend_pct:.0f}% in TREND")

    if eurusd_in_compression_pct > 40:
        print(f"  --> EURUSD is predominantly range-bound")
        print(f"  --> When EURUSD is in COMPRESSION, core instruments may also underperform")
        print(f"  --> Potential use as: 'low conviction' signal for core book risk reduction")

    # ── 7. Role Recommendation ───────────────────────────────
    print(f"\n  {'=' * 60}")
    print(f"  ROLE RECOMMENDATION")
    print(f"  {'=' * 60}")

    overall_exp = pnl_arr.mean()
    has_any_positive_regime = any(
        np.mean([s["pnl"] for s in signals if s["regime"] == r]) > 0.1
        for r in [REGIME_TREND, REGIME_EXPANSION, REGIME_COMPRESSION]
        if any(s["regime"] == r for s in signals)
    )

    # Check if mean reversion might work (losers had high MFE)
    mean_reversion_signal = len(loser_mfe) > 0 and np.median(loser_mfe) > 1.5

    print(f"\n  Overall expectancy:        {overall_exp:+.3f}R")
    print(f"  Any positive regime:       {has_any_positive_regime}")
    print(f"  Mean reversion potential:  {mean_reversion_signal}")
    print(f"  Compression time:          {eurusd_in_compression_pct:.0f}%")

    if overall_exp >= 0.05 and has_any_positive_regime:
        print(f"\n  >>> VERDICT: NICHE_TRADER")
        print(f"      Trade EURUSD only in specific positive regime/session combos")
    elif mean_reversion_signal:
        print(f"\n  >>> VERDICT: MEAN_REVERSION_CANDIDATE")
        print(f"      Losers had high MFE -> entries work, but trend exits don't")
        print(f"      Test with smaller TP (1R-1.5R) and faster exits")
    elif eurusd_in_compression_pct > 40:
        print(f"\n  >>> VERDICT: REGIME_FILTER")
        print(f"      EURUSD regime state as confidence modifier for core instruments")
        print(f"      When EURUSD compression -> reduce AGGRESSIVE mode threshold")
        print(f"      When EURUSD trend -> allow normal/aggressive in core book")
    else:
        print(f"\n  >>> VERDICT: REJECT")
        print(f"      No viable role found")

    print(f"\n  {'=' * 60}")


if __name__ == "__main__":
    main()
