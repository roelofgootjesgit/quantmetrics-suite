"""
Portfolio Optimization v2 — Core(3) vs Core(5) vs expanded stacks.

The key question: with USDCHF + NZDUSD added, do we still need NAS100 for challenge?

Tests:
  A. Core(3): XAU + GBP + JPY                       (previous baseline)
  B. Core(5): XAU + GBP + JPY + CHF + NZD            (new core)
  C. Core(5) + EURUSD MR                             (funded candidate)
  D. Core(5) + NAS100                                (challenge candidate)
  E. Core(5) + NAS100 + EURUSD MR                    (full stack)

For each: metrics, FTMO pass rate, funded projection, correlation analysis.

Usage:
    python scripts/portfolio_optimization_v2.py
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
from src.quantbuild.io.parquet_loader import load_parquet
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


# ── Exit functions (reused from multi_engine_test) ────────────────────

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
        if bar_idx >= 20:
            if partial_taken:
                return 0.5 * 0.5 + fav * 0.5
            return fav if fav > 0 else min(0, fav)
    if partial_taken:
        last_fav = exc[-1][0] if exc else 0
        return 0.5 * 0.5 + last_fav * 0.5
    return 0.0


# ── Signal generation ─────────────────────────────────────────────────

def generate_sqe_signals(symbol, cfg, inst_profile, base_path, start, end, use_nas_exit=False):
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
            })
    return signals


def generate_mr_signals(cfg, base_path, start, end):
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

    long_e = run_mr_conditions(data, "LONG", DEFAULT_MR_CONFIG, regime_series)
    short_e = run_mr_conditions(data, "SHORT", DEFAULT_MR_CONFIG, regime_series)
    sim_cache = _prepare_sim_cache(data)

    signals = []
    for i in range(1, len(data) - 1):
        for direction, mask in [("LONG", long_e), ("SHORT", short_e)]:
            if not mask.iloc[i]:
                continue
            ts = data.index[i]
            result = simulate_mr_trade(
                sim_cache, i, direction,
                tp_r=DEFAULT_MR_CONFIG["tp_r"],
                sl_r=DEFAULT_MR_CONFIG["sl_r"],
                time_stop_bars=DEFAULT_MR_CONFIG["time_stop_bars"],
            )
            signals.append({
                "ts": ts, "symbol": symbol, "direction": direction,
                "regime": REGIME_COMPRESSION, "session": "",
                "pnl_r": result["pnl_r"],
            })
    return signals


# ── Metrics ───────────────────────────────────────────────────────────

def compute_metrics(signals, label=""):
    if not signals:
        return {"label": label, "trades": 0, "wr": 0, "pf": 0, "exp": 0,
                "total_r": 0, "max_dd": 0, "rdd": 0, "trades_yr": 0}
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
        "wr": round(100 * len(wins) / len(pnl), 1),
        "pf": round(float(gw / gl), 2),
        "exp": round(float(pnl.mean()), 3),
        "total_r": round(float(pnl.sum()), 1),
        "max_dd": round(float(dd.min()), 1),
        "rdd": round(float(eq[-1] / abs(dd.min())) if dd.min() < 0 else 0, 2),
        "trades_yr": round(len(pnl) / (PERIOD_DAYS / 365.25), 0),
    }


def ftmo_monte_carlo(signals, n_sims=5000, n_days=30, target=10.0, max_dd=10.0, base_risk=1.5):
    if not signals:
        return {"pass_rate": 0, "avg_days": 0, "fail_dd": 0, "fail_timeout": 0}
    pnl_pool = np.array([s["pnl_r"] for s in signals])
    avg_per_day = len(pnl_pool) / (PERIOD_DAYS / 365.25) / 250

    passed = 0
    fail_dd = 0
    fail_timeout = 0
    pass_days = []

    for _ in range(n_sims):
        eq = 0.0
        peak_eq = 0.0
        blown = False
        for day in range(1, n_days + 1):
            trades_today = max(0, np.random.poisson(avg_per_day * 1.5))
            for _ in range(trades_today):
                raw = pnl_pool[np.random.randint(len(pnl_pool))]
                eq += raw * base_risk - 0.065 * base_risk
                peak_eq = max(peak_eq, eq)
                if peak_eq - eq >= max_dd:
                    blown = True
                    break
            if blown:
                fail_dd += 1
                break
            if eq >= target:
                passed += 1
                pass_days.append(day)
                break
        else:
            fail_timeout += 1

    return {
        "pass_rate": round(100 * passed / n_sims, 1),
        "avg_days": round(float(np.mean(pass_days)), 1) if pass_days else 0,
        "fail_dd": round(100 * fail_dd / n_sims, 1),
        "fail_timeout": round(100 * fail_timeout / n_sims, 1),
    }


# ── Correlation Analysis ──────────────────────────────────────────────

KNOWN_CORRELATIONS = {
    ("XAUUSD", "GBPUSD"): -0.03, ("XAUUSD", "USDJPY"): -0.001,
    ("XAUUSD", "USDCHF"): -0.15, ("XAUUSD", "NZDUSD"): 0.10,
    ("XAUUSD", "NAS100"): 0.05, ("XAUUSD", "EURUSD"): 0.15,
    ("GBPUSD", "USDJPY"): -0.001, ("GBPUSD", "USDCHF"): -0.55,
    ("GBPUSD", "NZDUSD"): 0.60, ("GBPUSD", "NAS100"): 0.02,
    ("GBPUSD", "EURUSD"): 0.55,
    ("USDJPY", "USDCHF"): 0.50, ("USDJPY", "NZDUSD"): -0.30,
    ("USDJPY", "NAS100"): -0.10, ("USDJPY", "EURUSD"): -0.25,
    ("USDCHF", "NZDUSD"): -0.55, ("USDCHF", "NAS100"): -0.05,
    ("USDCHF", "EURUSD"): -0.85,
    ("NZDUSD", "NAS100"): 0.10, ("NZDUSD", "EURUSD"): 0.55,
    ("NAS100", "EURUSD"): 0.05,
}


def get_corr(a, b):
    if a == b:
        return 1.0
    return KNOWN_CORRELATIONS.get((a, b), KNOWN_CORRELATIONS.get((b, a), 0.0))


def correlation_report(instrument_list):
    n = len(instrument_list)
    print(f"\n  Correlation matrix ({n} instruments):")
    print(f"  {'':>8s} " + " ".join(f"{s:>8s}" for s in instrument_list))
    for a in instrument_list:
        vals = " ".join(f"{get_corr(a, b):>8.2f}" for b in instrument_list)
        print(f"  {a:>8s} {vals}")

    pairwise = []
    high_corr_pairs = []
    for i in range(n):
        for j in range(i + 1, n):
            c = get_corr(instrument_list[i], instrument_list[j])
            pairwise.append(c)
            if abs(c) >= 0.50:
                high_corr_pairs.append((instrument_list[i], instrument_list[j], c))

    avg_abs = np.mean([abs(c) for c in pairwise]) if pairwise else 0
    print(f"\n  Avg absolute pairwise correlation: {avg_abs:.3f}")
    if high_corr_pairs:
        print(f"  HIGH CORRELATION PAIRS (|r| >= 0.50):")
        for a, b, c in sorted(high_corr_pairs, key=lambda x: -abs(x[2])):
            risk = "CLUSTER RISK" if abs(c) >= 0.60 else "MONITOR"
            print(f"    {a:>8s} <-> {b:<8s}: {c:+.2f}  [{risk}]")
    else:
        print(f"  No high-correlation pairs detected.")

    return avg_abs, high_corr_pairs


def loss_clustering_analysis(signals, label=""):
    """Check how often multiple instruments lose on the same day."""
    if not signals:
        return
    df = pd.DataFrame([{"ts": s["ts"], "sym": s["symbol"], "pnl": s["pnl_r"]} for s in signals])
    df["date"] = pd.to_datetime(df["ts"]).dt.date
    daily = df.groupby(["date", "sym"])["pnl"].sum().unstack(fill_value=0)

    n_instruments = daily.shape[1]
    losing = (daily < 0).sum(axis=1)
    cluster_2plus = int((losing >= 2).sum())
    cluster_3plus = int((losing >= 3).sum())
    cluster_all = int((losing >= n_instruments).sum())

    portfolio_daily = daily.sum(axis=1)
    worst_day = float(portfolio_daily.min())
    worst_week = float(portfolio_daily.rolling(5).sum().min()) if len(portfolio_daily) > 5 else worst_day

    print(f"\n  Loss clustering ({label}):")
    print(f"    2+ instruments losing same day: {cluster_2plus}")
    print(f"    3+ instruments losing same day: {cluster_3plus}")
    print(f"    ALL instruments losing same day: {cluster_all}")
    print(f"    Worst single day: {worst_day:+.1f}R")
    print(f"    Worst rolling 5-day: {worst_week:+.1f}R")


# ── Main ──────────────────────────────────────────────────────────────

def main():
    print("=" * 70)
    print("  PORTFOLIO OPTIMIZATION v2")
    print("  Core(3) vs Core(5) vs expanded stacks")
    print("  Key question: does Core(5) reduce need for NAS100?")
    print("=" * 70)

    cfg = load_config(CONFIG_PATH)
    setup_logging(cfg)
    with open(PROFILES_PATH) as f:
        profiles = yaml.safe_load(f)

    inst_profiles = profiles["instruments"]
    base_path = Path(cfg.get("data", {}).get("base_path", "data/market_cache"))
    end = datetime.now()
    start = end - timedelta(days=PERIOD_DAYS)

    # ── Generate signals per instrument ───────────────────────
    print("\n  GENERATING SIGNALS...")
    print("-" * 70)

    all_sigs = {}
    core3_syms = ["XAUUSD", "GBPUSD", "USDJPY"]
    core5_syms = ["XAUUSD", "GBPUSD", "USDJPY", "USDCHF", "NZDUSD"]

    for sym in core5_syms:
        inst = inst_profiles.get(sym, {})
        sigs = generate_sqe_signals(sym, cfg, inst, base_path, start, end)
        all_sigs[sym] = sigs
        print(f"    {sym:>8s}: {len(sigs):>5d} signals ({len(sigs)/(PERIOD_DAYS/365.25):.0f}/yr)")

    nas_inst = inst_profiles.get("NAS100", {})
    all_sigs["NAS100"] = generate_sqe_signals("NAS100", cfg, nas_inst, base_path, start, end, use_nas_exit=True)
    print(f"    {'NAS100':>8s}: {len(all_sigs['NAS100']):>5d} signals ({len(all_sigs['NAS100'])/(PERIOD_DAYS/365.25):.0f}/yr)")

    all_sigs["EURUSD_MR"] = generate_mr_signals(cfg, base_path, start, end)
    print(f"    {'EUR_MR':>8s}: {len(all_sigs['EURUSD_MR']):>5d} signals ({len(all_sigs['EURUSD_MR'])/(PERIOD_DAYS/365.25):.0f}/yr)")

    # ── Per-instrument metrics ────────────────────────────────
    print("\n" + "=" * 70)
    print("  PER-INSTRUMENT BREAKDOWN")
    print("=" * 70)

    print(f"\n  {'Instrument':>12s} {'Trades':>7s} {'Tr/yr':>6s} {'WR':>6s} {'PF':>6s} {'Exp':>7s} {'Total':>8s} {'DD':>7s} {'R/DD':>6s}")
    print(f"  {'-' * 72}")

    for sym in core5_syms + ["NAS100", "EURUSD_MR"]:
        m = compute_metrics(all_sigs[sym], sym)
        label = sym if sym != "EURUSD_MR" else "EUR_MR"
        if m["trades"] > 0:
            print(f"  {label:>12s} {m['trades']:>7d} {m['trades_yr']:>5.0f} {m['wr']:>5.1f}% {m['pf']:>6.2f} "
                  f"{m['exp']:>+6.3f}R {m['total_r']:>+7.1f}R {m['max_dd']:>+6.1f}R {m['rdd']:>5.2f}")
        else:
            print(f"  {label:>12s}       0     0    --     --      --       --      --    --")

    # ── Build scenarios ───────────────────────────────────────
    core3 = []
    for s in core3_syms:
        core3.extend(all_sigs[s])

    core5 = []
    for s in core5_syms:
        core5.extend(all_sigs[s])

    scenarios = {
        "A: Core(3)":                core3,
        "B: Core(5)":                core5,
        "C: Core(5) + EUR_MR":       core5 + all_sigs["EURUSD_MR"],
        "D: Core(5) + NAS100":       core5 + all_sigs["NAS100"],
        "E: Full (5+NAS+EUR)":       core5 + all_sigs["NAS100"] + all_sigs["EURUSD_MR"],
    }

    # ── Scenario comparison ───────────────────────────────────
    print("\n" + "=" * 70)
    print("  SCENARIO COMPARISON")
    print("=" * 70)

    print(f"\n  {'Scenario':<25s} {'Trades':>7s} {'Tr/yr':>6s} {'WR':>6s} {'PF':>6s} {'Exp':>7s} {'Total':>8s} {'DD':>7s} {'R/DD':>6s}")
    print(f"  {'-' * 78}")

    scenario_metrics = {}
    for name, sigs in scenarios.items():
        m = compute_metrics(sigs, name)
        scenario_metrics[name] = m
        if m["trades"] > 0:
            print(f"  {name:<25s} {m['trades']:>7d} {m['trades_yr']:>5.0f} {m['wr']:>5.1f}% {m['pf']:>6.2f} "
                  f"{m['exp']:>+6.3f}R {m['total_r']:>+7.1f}R {m['max_dd']:>+6.1f}R {m['rdd']:>5.02f}")

    # ── Core(3) vs Core(5) delta ──────────────────────────────
    m3 = scenario_metrics["A: Core(3)"]
    m5 = scenario_metrics["B: Core(5)"]
    print(f"\n  CORE(3) -> CORE(5) DELTA:")
    print(f"    Trades:  {m3['trades']} -> {m5['trades']} ({m5['trades'] - m3['trades']:+d})")
    print(f"    Tr/yr:   {m3['trades_yr']:.0f} -> {m5['trades_yr']:.0f} ({m5['trades_yr'] - m3['trades_yr']:+.0f})")
    print(f"    Exp:     {m3['exp']:+.3f}R -> {m5['exp']:+.3f}R ({m5['exp'] - m3['exp']:+.3f}R)")
    print(f"    Total:   {m3['total_r']:+.1f}R -> {m5['total_r']:+.1f}R ({m5['total_r'] - m3['total_r']:+.1f}R)")
    print(f"    DD:      {m3['max_dd']:.1f}R -> {m5['max_dd']:.1f}R ({m5['max_dd'] - m3['max_dd']:+.1f}R)")
    print(f"    R/DD:    {m3['rdd']:.2f} -> {m5['rdd']:.2f} ({m5['rdd'] - m3['rdd']:+.2f})")

    # ── Correlation analysis ──────────────────────────────────
    print("\n" + "=" * 70)
    print("  CORRELATION ANALYSIS")
    print("=" * 70)

    print("\n  Core(3):")
    correlation_report(core3_syms)

    print("\n  Core(5):")
    avg_corr_5, high_pairs_5 = correlation_report(core5_syms)

    print("\n  Full stack:")
    correlation_report(core5_syms + ["NAS100", "EURUSD"])

    # ── Loss clustering ───────────────────────────────────────
    print("\n" + "=" * 70)
    print("  LOSS CLUSTERING ANALYSIS")
    print("=" * 70)

    loss_clustering_analysis(core3, "Core(3)")
    loss_clustering_analysis(core5, "Core(5)")
    loss_clustering_analysis(core5 + all_sigs["NAS100"] + all_sigs["EURUSD_MR"], "Full stack")

    # ── FTMO Challenge ────────────────────────────────────────
    print("\n" + "=" * 70)
    print("  FTMO CHALLENGE SIMULATION (5,000 runs per scenario)")
    print("=" * 70)

    print(f"\n  {'Scenario':<25s} {'Pass%':>7s} {'Days':>6s} {'DD_Fail':>8s} {'Timeout':>8s}")
    print(f"  {'-' * 60}")

    for name, sigs in scenarios.items():
        ftmo = ftmo_monte_carlo(sigs, n_sims=5000)
        print(f"  {name:<25s} {ftmo['pass_rate']:>6.1f}% {ftmo['avg_days']:>5.0f}d "
              f"{ftmo['fail_dd']:>7.1f}% {ftmo['fail_timeout']:>7.1f}%")

    # ── Funded projection ─────────────────────────────────────
    print("\n" + "=" * 70)
    print("  FUNDED PROJECTION ($100K account, 0.5% risk)")
    print("=" * 70)

    risk_pct = 0.5
    print(f"\n  {'Scenario':<25s} {'Monthly%':>9s} {'Yearly%':>9s} {'$/mo':>9s} {'Max DD%':>9s}")
    print(f"  {'-' * 65}")

    for name, sigs in scenarios.items():
        m = scenario_metrics[name]
        if m["trades"] == 0:
            continue
        yearly_r = m["trades_yr"] * m["exp"]
        yearly_pct = yearly_r * risk_pct
        monthly_pct = yearly_pct / 12
        max_dd_pct = abs(m["max_dd"]) * risk_pct / (PERIOD_DAYS / 365.25)
        monthly_dollar = monthly_pct / 100 * 100_000
        print(f"  {name:<25s} {monthly_pct:>+8.2f}% {yearly_pct:>+8.1f}% "
              f"${monthly_dollar:>7,.0f} {max_dd_pct:>8.2f}%")

    # ── Key question: do we still need NAS100? ────────────────
    print("\n" + "=" * 70)
    print("  KEY QUESTION: IS NAS100 STILL NEEDED?")
    print("=" * 70)

    ftmo_b = ftmo_monte_carlo(scenarios["B: Core(5)"], n_sims=5000)
    ftmo_d = ftmo_monte_carlo(scenarios["D: Core(5) + NAS100"], n_sims=5000)
    ftmo_e = ftmo_monte_carlo(scenarios["E: Full (5+NAS+EUR)"], n_sims=5000)

    m_b = scenario_metrics["B: Core(5)"]
    m_d = scenario_metrics["D: Core(5) + NAS100"]

    print(f"\n  Core(5) alone:          {ftmo_b['pass_rate']:>5.1f}% pass  "
          f"({m_b['trades_yr']:.0f} tr/yr, timeout {ftmo_b['fail_timeout']:.0f}%)")
    print(f"  Core(5) + NAS100:       {ftmo_d['pass_rate']:>5.1f}% pass  "
          f"({m_d['trades_yr']:.0f} tr/yr, timeout {ftmo_d['fail_timeout']:.0f}%)")
    print(f"  Full stack:             {ftmo_e['pass_rate']:>5.1f}% pass")

    nas_uplift = ftmo_d["pass_rate"] - ftmo_b["pass_rate"]
    print(f"\n  NAS100 uplift:          {nas_uplift:+.1f}% pass rate")
    print(f"  NAS100 timeout fix:     {ftmo_b['fail_timeout'] - ftmo_d['fail_timeout']:+.1f}% timeout reduction")

    if ftmo_b["pass_rate"] >= 55:
        print(f"\n  VERDICT: Core(5) alone may be sufficient for challenge (>{55}% pass)")
        print(f"  NAS100 optional throughput boost, not critical")
    elif nas_uplift > 10:
        print(f"\n  VERDICT: NAS100 still significantly improves challenge pass rate")
        print(f"  Keep as CHALLENGE_CANDIDATE")
    else:
        print(f"\n  VERDICT: NAS100 provides marginal improvement")
        print(f"  Consider keeping for throughput but monitor DD impact")

    # ── Recommended config ────────────────────────────────────
    print("\n" + "=" * 70)
    print("  RECOMMENDED DEPLOYMENT")
    print("=" * 70)

    mc = scenario_metrics["C: Core(5) + EUR_MR"]
    me = scenario_metrics["E: Full (5+NAS+EUR)"]
    ftmo_c = ftmo_monte_carlo(scenarios["C: Core(5) + EUR_MR"], n_sims=5000)

    print(f"\n  FUNDED:     Core(5) + EURUSD MR")
    print(f"              {mc['trades_yr']:.0f} trades/yr  exp {mc['exp']:+.3f}R  R/DD {mc['rdd']:.2f}")
    print(f"              Monthly: {mc['trades_yr'] * mc['exp'] * risk_pct / 12:+.2f}%  (~${mc['trades_yr'] * mc['exp'] * risk_pct / 12 / 100 * 100_000:,.0f}/mo)")

    print(f"\n  CHALLENGE:  Core(5) + NAS100 (+ pass accelerator)")
    print(f"              {m_d['trades_yr']:.0f} trades/yr  pass rate: {ftmo_d['pass_rate']:.1f}%")

    print(f"\n  MAX STACK:  Core(5) + NAS100 + EURUSD MR")
    print(f"              {me['trades_yr']:.0f} trades/yr  pass rate: {ftmo_e['pass_rate']:.1f}%")

    # ── FX cluster warning ────────────────────────────────────
    if high_pairs_5:
        print(f"\n  FX CLUSTER WARNING:")
        print(f"  High-correlation pairs in Core(5):")
        for a, b, c in high_pairs_5:
            print(f"    {a} <-> {b}: {c:+.2f}")
        print(f"  Recommendation: cap combined heat for correlated FX pairs")
        print(f"  Suggested: max 2 concurrent trades from GBP+NZD cluster")

    print("\n" + "=" * 70)
    print("  Done.")
    print("=" * 70)


if __name__ == "__main__":
    main()
