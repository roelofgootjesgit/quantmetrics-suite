"""
Regime x Session x News analytics for STRICT_PROD_V1.

Runs the production backtest and produces a deep breakdown of:
  1. Per-regime metrics (TREND / EXPANSION / COMPRESSION shadow)
  2. Per-session within regime
  3. MAE/MFE analysis per regime
  4. Expansion sub-analysis (early/late, London/NY, with/without sweep)
  5. News module quantification (blocked vs passed, aligned vs misaligned)
  6. Yearly regime distribution

Usage:
    python scripts/regime_analytics.py
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
    run_backtest, _deep_merge, _simulate_trade, _prepare_sim_cache,
    _apply_h1_gate, _setup_news_gate,
)
from src.quantbuild.backtest.metrics import compute_metrics
from src.quantbuild.data.sessions import session_from_timestamp
from src.quantbuild.io.parquet_loader import load_parquet, ensure_data
from src.quantbuild.strategies.sqe_xauusd import (
    run_sqe_conditions, get_sqe_default_config, _compute_modules_once,
)
from src.quantbuild.strategy_modules.regime.detector import (
    RegimeDetector, REGIME_TREND, REGIME_EXPANSION, REGIME_COMPRESSION,
)

PERIOD_DAYS = 1825
CONFIG_PATH = "configs/strict_prod_v1.yaml"


def _metrics_for_trades(trades):
    """Compute detailed metrics dict from a list of trade dicts (not Trade objects)."""
    if not trades:
        return {
            "n": 0, "wins": 0, "losses": 0, "wr": 0.0, "pf": 0.0,
            "expectancy": 0.0, "total_r": 0.0, "max_dd": 0.0,
            "avg_mae_r": 0.0, "avg_mfe_r": 0.0, "avg_holding_h": 0.0,
            "avg_win_r": 0.0, "avg_loss_r": 0.0,
        }

    wins = [t for t in trades if t["result"] == "WIN"]
    losses = [t for t in trades if t["result"] == "LOSS"]
    total_r = sum(t["profit_r"] for t in trades)
    gross_win = sum(t["profit_r"] for t in wins) if wins else 0.0
    gross_loss = abs(sum(t["profit_r"] for t in losses)) if losses else 0.0
    pf = (gross_win / gross_loss) if gross_loss else (gross_win or 0.0)

    equity = []
    cum = 0.0
    for t in trades:
        cum += t["profit_r"]
        equity.append(cum)
    peak = equity[0]
    max_dd = 0.0
    for v in equity:
        if v > peak:
            peak = v
        dd = peak - v
        if dd > max_dd:
            max_dd = dd

    avg_mae = np.mean([t.get("mae_r", 0) for t in trades])
    avg_mfe = np.mean([t.get("mfe_r", 0) for t in trades])
    holding_h = [(t["exit_ts"] - t["entry_ts"]).total_seconds() / 3600
                 for t in trades if hasattr(t.get("exit_ts"), "hour")]
    avg_hold = np.mean(holding_h) if holding_h else 0.0
    avg_win_r = np.mean([t["profit_r"] for t in wins]) if wins else 0.0
    avg_loss_r = np.mean([t["profit_r"] for t in losses]) if losses else 0.0

    return {
        "n": len(trades), "wins": len(wins), "losses": len(losses),
        "wr": 100 * len(wins) / len(trades),
        "pf": pf, "expectancy": total_r / len(trades), "total_r": total_r,
        "max_dd": -max_dd,
        "avg_mae_r": float(avg_mae), "avg_mfe_r": float(avg_mfe),
        "avg_holding_h": float(avg_hold),
        "avg_win_r": float(avg_win_r), "avg_loss_r": float(avg_loss_r),
    }


def _print_metrics(label, m, indent=2):
    pad = " " * indent
    print(f"\n{pad}{label}")
    print(f"{pad}{'-' * len(label)}")
    print(f"{pad}Trades:       {m['n']:>6d}   (W:{m['wins']} L:{m['losses']})")
    print(f"{pad}Win Rate:     {m['wr']:>6.1f}%")
    print(f"{pad}PF:           {m['pf']:>6.2f}")
    print(f"{pad}Expectancy:   {m['expectancy']:>6.3f}R")
    print(f"{pad}Total R:      {m['total_r']:>+6.1f}R")
    print(f"{pad}Max DD:       {m['max_dd']:>6.1f}R")
    print(f"{pad}Avg MAE:      {m['avg_mae_r']:>6.2f}R")
    print(f"{pad}Avg MFE:      {m['avg_mfe_r']:>6.2f}R")
    print(f"{pad}Avg Win:      {m['avg_win_r']:>+6.2f}R")
    print(f"{pad}Avg Loss:     {m['avg_loss_r']:>+6.2f}R")
    print(f"{pad}Avg Hold:     {m['avg_holding_h']:>6.1f}h")


def run_full_analysis():
    print("=" * 70)
    print("  STRICT_PROD_V1 -- Regime x Session x News Analytics")
    print("=" * 70)

    cfg = load_config(CONFIG_PATH)
    setup_logging(cfg)

    symbol = cfg.get("symbol", "XAUUSD")
    base_path = Path(cfg.get("data", {}).get("base_path", "data/market_cache"))
    tp_r = cfg["backtest"]["tp_r"]
    sl_r = cfg["backtest"]["sl_r"]
    session_mode = cfg["backtest"].get("session_mode", "extended")

    end = datetime.now()
    start = end - timedelta(days=PERIOD_DAYS)

    data_15m = load_parquet(base_path, symbol, "15m", start=start, end=end)
    data_1h = load_parquet(base_path, symbol, "1h", start=start, end=end)
    if data_15m.empty or len(data_15m) < 50:
        data_15m = ensure_data(symbol=symbol, timeframe="15m", base_path=base_path, period_days=PERIOD_DAYS)
    data_15m = data_15m.sort_index()
    if not data_1h.empty:
        data_1h = data_1h.sort_index()

    print(f"\n  Data: {len(data_15m):,} bars (15m), {len(data_1h):,} bars (1h)")
    print(f"  Range: {data_15m.index[0]} -> {data_15m.index[-1]}")

    # --- Regime detection ---
    regime_cfg = cfg.get("regime", {})
    detector = RegimeDetector(config=regime_cfg)
    regime_series = detector.classify(data_15m, data_1h if not data_1h.empty else None)

    print("\n" + "=" * 70)
    print("  SECTION 1: REGIME DISTRIBUTION")
    print("=" * 70)

    for year in sorted(set(data_15m.index.year)):
        mask = data_15m.index.year == year
        yr_regimes = regime_series[mask]
        total = len(yr_regimes)
        for r in [REGIME_TREND, REGIME_EXPANSION, REGIME_COMPRESSION]:
            cnt = (yr_regimes == r).sum()
            print(f"  {year}  {r:>15s}: {cnt:>6,} bars ({100*cnt/total:>5.1f}%)")
        print()

    # --- Generate all entry signals (no regime filtering) ---
    sqe_cfg = get_sqe_default_config()
    strategy_cfg = cfg.get("strategy", {}) or {}
    if strategy_cfg:
        _deep_merge(sqe_cfg, strategy_cfg)

    precomputed_df = _compute_modules_once(data_15m, sqe_cfg)
    long_entries = run_sqe_conditions(data_15m, "LONG", sqe_cfg, _precomputed_df=precomputed_df)
    short_entries = run_sqe_conditions(data_15m, "SHORT", sqe_cfg, _precomputed_df=precomputed_df)

    if strategy_cfg.get("structure_use_h1_gate", False) and not data_1h.empty:
        long_entries = _apply_h1_gate(long_entries, data_15m, "LONG", base_path, symbol, start, end, sqe_cfg)
        short_entries = _apply_h1_gate(short_entries, data_15m, "SHORT", base_path, symbol, start, end, sqe_cfg)

    # --- Simulate ALL trades (ignoring regime filter) to get shadow data ---
    sim_cache = _prepare_sim_cache(data_15m)
    all_trades = []

    for i in range(1, len(data_15m) - 1):
        directions = []
        if long_entries.iloc[i]:
            directions.append("LONG")
        if short_entries.iloc[i]:
            directions.append("SHORT")

        for direction in directions:
            entry_ts = data_15m.index[i]
            regime = regime_series.iloc[i] if i < len(regime_series) else None
            session = session_from_timestamp(entry_ts, mode=session_mode)

            result = _simulate_trade(data_15m, i, direction, tp_r, sl_r, _cache=sim_cache)

            has_sweep = False
            if "sweep_bull" in precomputed_df.columns:
                if direction == "LONG":
                    has_sweep = bool(precomputed_df["sweep_bull"].iloc[i]) if i < len(precomputed_df) else False
                else:
                    has_sweep = bool(precomputed_df["sweep_bear"].iloc[i]) if i < len(precomputed_df) else False

            all_trades.append({
                "entry_ts": entry_ts,
                "exit_ts": result["exit_ts"],
                "direction": direction,
                "regime": regime,
                "session": session,
                "year": entry_ts.year,
                "hour": entry_ts.hour,
                "result": result["result"],
                "profit_r": result["profit_r"],
                "profit_usd": result["profit_usd"],
                "entry_price": result["entry_price"],
                "exit_price": result["exit_price"],
                "sl": result["sl"],
                "tp": result["tp"],
                "atr": result["atr"],
                "mae_r": result["mae_r"],
                "mfe_r": result["mfe_r"],
                "has_sweep": has_sweep,
            })

    print(f"  Total signals (all regimes): {len(all_trades)}")

    # =========================================================
    # SECTION 2: PER-REGIME METRICS
    # =========================================================
    print("\n" + "=" * 70)
    print("  SECTION 2: PER-REGIME METRICS (all trades, no session limit)")
    print("=" * 70)

    by_regime = defaultdict(list)
    for t in all_trades:
        by_regime[t["regime"] or "unknown"].append(t)

    for regime_name in [REGIME_TREND, REGIME_EXPANSION, REGIME_COMPRESSION]:
        trades = by_regime.get(regime_name, [])
        m = _metrics_for_trades(trades)
        _print_metrics(f"REGIME: {regime_name.upper()}", m)

        # Direction split within regime
        for d in ["LONG", "SHORT"]:
            d_trades = [t for t in trades if t["direction"] == d]
            if d_trades:
                dm = _metrics_for_trades(d_trades)
                print(f"      {d}: {dm['n']} trades, WR {dm['wr']:.1f}%, "
                      f"PF {dm['pf']:.2f}, {dm['total_r']:+.1f}R")

    # =========================================================
    # SECTION 3: REGIME x SESSION CROSS-TAB
    # =========================================================
    print("\n" + "=" * 70)
    print("  SECTION 3: REGIME x SESSION")
    print("=" * 70)

    header = f"  {'Regime':<15s} {'Session':<12s} {'N':>5s} {'WR':>6s} {'PF':>6s} {'Exp':>7s} {'R':>8s} {'MAE':>6s} {'MFE':>6s}"
    print(header)
    print("  " + "-" * (len(header) - 2))

    for regime_name in [REGIME_TREND, REGIME_EXPANSION, REGIME_COMPRESSION]:
        for session_name in ["London", "Overlap", "New York", "Asia"]:
            trades = [t for t in all_trades
                      if t["regime"] == regime_name and t["session"] == session_name]
            if not trades:
                continue
            m = _metrics_for_trades(trades)
            print(f"  {regime_name:<15s} {session_name:<12s} {m['n']:>5d} {m['wr']:>5.1f}% "
                  f"{m['pf']:>6.2f} {m['expectancy']:>+6.3f}R {m['total_r']:>+7.1f}R "
                  f"{m['avg_mae_r']:>5.2f}R {m['avg_mfe_r']:>5.2f}R")

    # =========================================================
    # SECTION 4: EXPANSION DEEP DIVE
    # =========================================================
    print("\n" + "=" * 70)
    print("  SECTION 4: EXPANSION DEEP DIVE")
    print("=" * 70)

    exp_trades = by_regime.get(REGIME_EXPANSION, [])
    if exp_trades:
        # Early expansion (first 4h after regime onset) vs late
        # Approximate: hour < 10 = early session, hour >= 10 = late
        early = [t for t in exp_trades if t["hour"] < 10]
        late = [t for t in exp_trades if t["hour"] >= 10]
        _print_metrics("EXPANSION - Early (before 10:00 UTC)", _metrics_for_trades(early), indent=4)
        _print_metrics("EXPANSION - Late (10:00+ UTC)", _metrics_for_trades(late), indent=4)

        # London vs NY
        london = [t for t in exp_trades if t["session"] == "London"]
        ny = [t for t in exp_trades if t["session"] in ("New York", "Overlap")]
        _print_metrics("EXPANSION - London", _metrics_for_trades(london), indent=4)
        _print_metrics("EXPANSION - NY+Overlap", _metrics_for_trades(ny), indent=4)

        # With sweep vs without
        with_sweep = [t for t in exp_trades if t["has_sweep"]]
        no_sweep = [t for t in exp_trades if not t["has_sweep"]]
        _print_metrics("EXPANSION - With Sweep", _metrics_for_trades(with_sweep), indent=4)
        _print_metrics("EXPANSION - No Sweep", _metrics_for_trades(no_sweep), indent=4)

        # Year by year
        print("\n    EXPANSION yearly:")
        for year in sorted(set(t["year"] for t in exp_trades)):
            yr = [t for t in exp_trades if t["year"] == year]
            m = _metrics_for_trades(yr)
            print(f"      {year}: {m['n']:>3d} trades, WR {m['wr']:>5.1f}%, "
                  f"PF {m['pf']:.2f}, {m['total_r']:>+6.1f}R, "
                  f"MAE {m['avg_mae_r']:.2f}R, MFE {m['avg_mfe_r']:.2f}R")
    else:
        print("  No expansion trades found.")

    # =========================================================
    # SECTION 5: COMPRESSION SHADOW ANALYSIS
    # =========================================================
    print("\n" + "=" * 70)
    print("  SECTION 5: COMPRESSION SHADOW (what we skip)")
    print("=" * 70)

    comp_trades = by_regime.get(REGIME_COMPRESSION, [])
    if comp_trades:
        m = _metrics_for_trades(comp_trades)
        _print_metrics("COMPRESSION (shadow - not actually traded)", m)
        print(f"\n    By skipping these {m['n']} trades, SKIP_COMP avoids:")
        print(f"    - {m['losses']} losing trades")
        print(f"    - {abs(m['total_r']):.1f}R of {'losses' if m['total_r'] < 0 else 'gains'}")
        if m["total_r"] < 0:
            print(f"    --> Net benefit of skipping: +{abs(m['total_r']):.1f}R saved")
        else:
            print(f"    --> Cost of skipping: {m['total_r']:.1f}R foregone")

        # Year by year
        print("\n    COMPRESSION yearly:")
        for year in sorted(set(t["year"] for t in comp_trades)):
            yr = [t for t in comp_trades if t["year"] == year]
            ym = _metrics_for_trades(yr)
            print(f"      {year}: {ym['n']:>3d} trades, WR {ym['wr']:>5.1f}%, "
                  f"{ym['total_r']:>+6.1f}R {'(skip saves R)' if ym['total_r'] < 0 else '(skip costs R)'}")

    # =========================================================
    # SECTION 6: SKIP_COMP vs BASELINE side-by-side
    # =========================================================
    print("\n" + "=" * 70)
    print("  SECTION 6: SKIP_COMP vs BASELINE")
    print("=" * 70)

    baseline_trades = all_trades
    skipcomp_trades = [t for t in all_trades if t["regime"] != REGIME_COMPRESSION]

    bm = _metrics_for_trades(baseline_trades)
    sm = _metrics_for_trades(skipcomp_trades)

    header = f"  {'Metric':<20s} {'BASELINE':>12s} {'SKIP_COMP':>12s} {'Delta':>12s}"
    print(header)
    print("  " + "-" * (len(header) - 2))
    for label, bv, sv, fmt in [
        ("Trades", bm["n"], sm["n"], "d"),
        ("Win Rate", bm["wr"], sm["wr"], ".1f"),
        ("PF", bm["pf"], sm["pf"], ".2f"),
        ("Expectancy", bm["expectancy"], sm["expectancy"], ".3f"),
        ("Total R", bm["total_r"], sm["total_r"], ".1f"),
        ("Max DD", bm["max_dd"], sm["max_dd"], ".1f"),
        ("R/DD ratio", bm["total_r"]/abs(bm["max_dd"]) if bm["max_dd"] else 0,
         sm["total_r"]/abs(sm["max_dd"]) if sm["max_dd"] else 0, ".2f"),
        ("Avg MAE", bm["avg_mae_r"], sm["avg_mae_r"], ".2f"),
        ("Avg MFE", bm["avg_mfe_r"], sm["avg_mfe_r"], ".2f"),
    ]:
        delta = sv - bv
        sign = "+" if delta >= 0 else ""
        fmt_str = f"{{:>{12}{fmt}}}"
        print(f"  {label:<20s} {format(bv, fmt):>12s} {format(sv, fmt):>12s} "
              f"{sign}{format(delta, fmt):>11s}")

    # =========================================================
    # SECTION 7: YEARLY REGIME CONTRIBUTION
    # =========================================================
    print("\n" + "=" * 70)
    print("  SECTION 7: YEARLY REGIME CONTRIBUTION (SKIP_COMP)")
    print("=" * 70)

    print(f"  {'Year':<6s} {'TREND':>10s} {'EXPANSION':>12s} {'Total':>10s}")
    print("  " + "-" * 44)

    for year in sorted(set(t["year"] for t in skipcomp_trades)):
        for_year = [t for t in skipcomp_trades if t["year"] == year]
        trend_yr = [t for t in for_year if t["regime"] == REGIME_TREND]
        exp_yr = [t for t in for_year if t["regime"] == REGIME_EXPANSION]

        trend_r = sum(t["profit_r"] for t in trend_yr) if trend_yr else 0
        exp_r = sum(t["profit_r"] for t in exp_yr) if exp_yr else 0
        total_r = sum(t["profit_r"] for t in for_year)

        print(f"  {year:<6d} {trend_r:>+9.1f}R {exp_r:>+11.1f}R {total_r:>+9.1f}R")

    # =========================================================
    # SECTION 8: MAE/MFE EFFICIENCY
    # =========================================================
    print("\n" + "=" * 70)
    print("  SECTION 8: MAE/MFE TRADE EFFICIENCY")
    print("=" * 70)

    for regime_name in [REGIME_TREND, REGIME_EXPANSION]:
        trades = by_regime.get(regime_name, [])
        if not trades:
            continue
        wins = [t for t in trades if t["result"] == "WIN"]
        losses = [t for t in trades if t["result"] == "LOSS"]
        print(f"\n  {regime_name.upper()}")
        if wins:
            print(f"    Winning trades ({len(wins)}):")
            print(f"      Avg MAE: {np.mean([t['mae_r'] for t in wins]):.2f}R "
                  f"(how far against before winning)")
            print(f"      Avg MFE: {np.mean([t['mfe_r'] for t in wins]):.2f}R "
                  f"(max favorable before exit)")
        if losses:
            print(f"    Losing trades ({len(losses)}):")
            print(f"      Avg MAE: {np.mean([t['mae_r'] for t in losses]):.2f}R")
            print(f"      Avg MFE: {np.mean([t['mfe_r'] for t in losses]):.2f}R "
                  f"(was profitable before stopping out)")

    # =========================================================
    # SAVE RESULTS
    # =========================================================
    report_dir = Path("reports/latest")
    report_dir.mkdir(parents=True, exist_ok=True)

    summary = {
        "config": "STRICT_PROD_V1",
        "period_days": PERIOD_DAYS,
        "total_signals": len(all_trades),
        "baseline": bm,
        "skip_comp": sm,
        "by_regime": {r: _metrics_for_trades(by_regime.get(r, []))
                      for r in [REGIME_TREND, REGIME_EXPANSION, REGIME_COMPRESSION]},
    }
    path = report_dir / "regime_analytics.json"
    with open(path, "w") as f:
        json.dump(summary, f, indent=2, default=str)
    print(f"\n  Results saved to {path}")
    print("=" * 70)


if __name__ == "__main__":
    run_full_analysis()
