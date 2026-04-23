"""
Dual-Book FTMO Simulation — the decisive 3-scenario comparison.

Scenario A: Core only (XAUUSD + GBPUSD + USDJPY)
Scenario B: Core + NAS100 throughput book
Scenario C: Core + NAS100 + Pass Accelerator

Each scenario tested for both CHALLENGE and FUNDED viability.
10,000 Monte Carlo paths per scenario.

Usage:
    python scripts/dual_book_ftmo_sim.py
"""
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import yaml

from src.quantbuild.config import load_config
from src.quantbuild.logging_config import setup_logging
from src.quantbuild.execution.adaptive_mode import AdaptiveModeLayer
from src.quantbuild.execution.portfolio_heat import PortfolioHeatEngine
from src.quantbuild.execution.pass_accelerator import PassAccelerator

logging.disable(logging.INFO)

CONFIG_PATH = "configs/strict_prod_v2.yaml"
PROFILES_PATH = "configs/instruments/instrument_profiles.yaml"
N_SIMS = 10_000
CHALLENGE_DAYS = 30
FUNDED_MONTHS = 12


def build_signal_pools():
    """Build separate signal pools for core and throughput books from validated stats."""
    np.random.seed(42)

    core_signals = []

    # XAUUSD: ~69 trades/5yr, exp ~0.32R, WR ~42%
    for _ in range(69):
        pnl = np.random.choice([2.0, 1.5, 1.0, 0.5, -1.0], p=[0.20, 0.12, 0.10, 0.05, 0.53])
        core_signals.append({"symbol": "XAUUSD", "pnl_r": float(pnl), "asset_class": "metals", "regime": "trend"})

    # GBPUSD: ~6 trades/5yr (TREND only), exp ~0.60R
    for _ in range(6):
        pnl = np.random.choice([2.0, 1.5, -1.0], p=[0.40, 0.20, 0.40])
        core_signals.append({"symbol": "GBPUSD", "pnl_r": float(pnl), "asset_class": "fx_major", "regime": "trend"})

    # USDJPY: ~4 trades/5yr, exp ~0.33R
    for _ in range(4):
        pnl = np.random.choice([2.0, 1.0, -1.0], p=[0.35, 0.15, 0.50])
        core_signals.append({"symbol": "USDJPY", "pnl_r": float(pnl), "asset_class": "fx_major", "regime": "trend"})

    throughput_signals = []

    # NAS100 TREND-only: ~956 trades/5yr = ~191/yr, exp +0.106R, WR ~43%
    for _ in range(956):
        pnl = np.random.choice(
            [3.0, 2.0, 1.5, 1.0, 0.5, -1.0],
            p=[0.05, 0.15, 0.10, 0.08, 0.05, 0.57]
        )
        throughput_signals.append({"symbol": "NAS100", "pnl_r": float(pnl), "asset_class": "index_us", "regime": "trend"})

    return core_signals, throughput_signals


def simulate_challenge(
    signal_pool, mode_config, inst_profiles,
    use_accelerator=False, n_sims=N_SIMS, n_days=CHALLENGE_DAYS,
):
    """Monte Carlo FTMO challenge simulation."""
    target = mode_config.get("target_pct", 10.0)
    max_daily = mode_config.get("max_daily_loss_pct", 5.0)
    max_total = mode_config.get("max_total_dd_pct", 10.0)
    base_risk = mode_config.get("risk_per_trade_pct", 1.5)

    avg_trades_day = len(signal_pool) / (5 * 250)

    pnl_arr = np.array([s["pnl_r"] for s in signal_pool])
    sym_arr = [s["symbol"] for s in signal_pool]
    asset_arr = [s["asset_class"] for s in signal_pool]

    res = {"passed": 0, "failed_dd": 0, "failed_timeout": 0,
           "pass_days": [], "finals": [], "max_dds": [], "by_symbol": {}}

    for _ in range(n_sims):
        adapt = AdaptiveModeLayer({"adaptive_mode": {
            "aggressive_dd_max": 1.5, "defensive_dd": 3.0, "lockdown_dd": max_total * 0.8,
        }})

        accel = None
        if use_accelerator:
            accel = PassAccelerator({"pass_accelerator": {
                "target_pct": target, "max_total_dd_pct": max_total,
                "challenge_days": n_days, "attack_until_day": 10,
                "secure_at_pct": target * 0.7, "coast_at_pct": target * 0.9,
                "dd_danger_zone_pct": max_total * 0.3,
            }})
            accel.start_challenge()

        eq = 0.0
        peak = 0.0
        passed = False
        day_pass = n_days
        max_dd = 0.0
        sym_pnl = {}

        for day in range(1, n_days + 1):
            daily = 0.0
            trades_today = max(0, np.random.poisson(avg_trades_day * 1.5))

            if use_accelerator:
                accel.update(eq, day)
                if accel.phase == "ATTACK":
                    trades_today = max(trades_today, np.random.poisson(avg_trades_day * 2.5))
                elif accel.phase == "COAST":
                    trades_today = min(trades_today, 1)

            for _ in range(trades_today):
                idx = np.random.randint(0, len(pnl_arr))
                raw = pnl_arr[idx]
                sym = sym_arr[idx]

                risk_mult = adapt.risk_multiplier
                inst_mult = inst_profiles.get(sym, {}).get("risk_multiplier", 1.0)
                if use_accelerator:
                    risk_mult = accel.get_effective_risk(inst_mult, adapt.risk_multiplier)
                else:
                    risk_mult *= inst_mult

                effective = base_risk * risk_mult
                t_pnl = raw * effective - 0.065 * effective  # slippage

                daily += t_pnl
                eq += t_pnl

                sym_pnl.setdefault(sym, 0.0)
                sym_pnl[sym] += t_pnl

                adapt.update_equity(eq)
                adapt.record_trade(raw, symbol=sym)
                if use_accelerator:
                    accel.record_trade(str(day))
                    accel.update(eq, day)

                peak = max(peak, eq)
                max_dd = max(max_dd, peak - eq)

            if abs(daily) >= max_daily or max_dd >= max_total:
                res["failed_dd"] += 1
                break
            if eq >= target:
                res["passed"] += 1
                day_pass = day
                passed = True
                break
        else:
            if not passed:
                res["failed_timeout"] += 1

        res["pass_days"].append(day_pass)
        res["finals"].append(eq)
        res["max_dds"].append(max_dd)
        for s, p in sym_pnl.items():
            res["by_symbol"].setdefault(s, [])
            res["by_symbol"][s].append(p)

    res["pass_rate"] = 100 * res["passed"] / n_sims
    res["avg_pass_day"] = float(np.mean([d for d in res["pass_days"] if d < n_days])) if res["passed"] else 0
    res["avg_eq"] = float(np.mean(res["finals"]))
    res["avg_dd"] = float(np.mean(res["max_dds"]))
    return res


def simulate_funded(
    signal_pool, mode_config, inst_profiles,
    n_sims=N_SIMS, n_months=FUNDED_MONTHS,
):
    """Monte Carlo funded account simulation (monthly returns)."""
    max_daily = mode_config.get("max_daily_loss_pct", 2.0)
    max_total = mode_config.get("max_total_dd_pct", 6.0)
    base_risk = mode_config.get("risk_per_trade_pct", 0.75)

    avg_trades_day = len(signal_pool) / (5 * 250)
    pnl_arr = np.array([s["pnl_r"] for s in signal_pool])
    sym_arr = [s["symbol"] for s in signal_pool]

    monthly_returns = []
    blown = 0

    for _ in range(n_sims):
        adapt = AdaptiveModeLayer({"adaptive_mode": {
            "aggressive_dd_max": 1.0, "defensive_dd": 2.0, "lockdown_dd": max_total * 0.7,
        }})

        eq = 0.0
        peak = 0.0
        monthly = []
        account_blown = False

        for month in range(n_months):
            month_pnl = 0.0
            for day in range(22):
                daily = 0.0
                trades = max(0, np.random.poisson(avg_trades_day * 1.2))
                for _ in range(trades):
                    idx = np.random.randint(0, len(pnl_arr))
                    raw = pnl_arr[idx]
                    sym = sym_arr[idx]
                    inst_mult = inst_profiles.get(sym, {}).get("risk_multiplier", 1.0)
                    effective = base_risk * adapt.risk_multiplier * inst_mult
                    t_pnl = raw * effective - 0.065 * effective
                    daily += t_pnl
                    eq += t_pnl
                    adapt.update_equity(eq)
                    adapt.record_trade(raw, symbol=sym)
                    peak = max(peak, eq)

                if abs(daily) >= max_daily or (peak - eq) >= max_total:
                    account_blown = True
                    break
                month_pnl += daily

            if account_blown:
                blown += 1
                break
            monthly.append(month_pnl)

        monthly_returns.append(monthly)

    all_monthly = [m for sim in monthly_returns for m in sim]
    return {
        "avg_monthly": float(np.mean(all_monthly)) if all_monthly else 0,
        "median_monthly": float(np.median(all_monthly)) if all_monthly else 0,
        "std_monthly": float(np.std(all_monthly)) if all_monthly else 0,
        "worst_monthly": float(np.min(all_monthly)) if all_monthly else 0,
        "blown_pct": 100 * blown / n_sims,
        "positive_months_pct": 100 * sum(1 for m in all_monthly if m > 0) / len(all_monthly) if all_monthly else 0,
    }


def print_results(label, ch_res, fund_res=None):
    print(f"\n  {'=' * 60}")
    print(f"  {label}")
    print(f"  {'=' * 60}")

    print(f"\n  CHALLENGE (10% in 30d, max 5% daily DD, max 10% total DD)")
    print(f"    Pass rate:       {ch_res['pass_rate']:.1f}%")
    print(f"    Avg pass day:    {ch_res['avg_pass_day']:.0f}")
    print(f"    Avg final eq:    {ch_res['avg_eq']:+.1f}%")
    print(f"    Avg max DD:      {ch_res['avg_dd']:.1f}%")
    print(f"    Failed DD:       {ch_res['failed_dd']:,}")
    print(f"    Failed timeout:  {ch_res['failed_timeout']:,}")

    # Per-symbol PnL contribution
    if ch_res.get("by_symbol"):
        print(f"    Per-symbol avg contribution:")
        for sym in sorted(ch_res["by_symbol"]):
            vals = ch_res["by_symbol"][sym]
            avg = np.mean(vals)
            print(f"      {sym:<10s}: {avg:+.2f}%")

    # FTMO business case
    pr = ch_res["pass_rate"] / 100
    if pr > 0:
        cost = 155
        payout = 8000
        net_ev = pr * payout - cost
        print(f"\n    FTMO Business Case:")
        print(f"      Net EV/attempt:    ${net_ev:+,.0f}")
        print(f"      Attempts to pass:  {1/pr:.1f}")
        print(f"      Cost to 1 pass:    ${cost/pr:,.0f}")

    if fund_res:
        print(f"\n  FUNDED (12 months, max 2% daily DD, max 6% total DD)")
        print(f"    Avg monthly:     {fund_res['avg_monthly']:+.2f}%")
        print(f"    Median monthly:  {fund_res['median_monthly']:+.2f}%")
        print(f"    Std monthly:     {fund_res['std_monthly']:.2f}%")
        print(f"    Worst month:     {fund_res['worst_monthly']:+.2f}%")
        print(f"    Blown accounts:  {fund_res['blown_pct']:.1f}%")
        print(f"    Positive months: {fund_res['positive_months_pct']:.0f}%")


def main():
    print("=" * 70)
    print("  DUAL-BOOK FTMO SIMULATION")
    print("  Scenario A: Core only")
    print("  Scenario B: Core + NAS100 throughput")
    print("  Scenario C: Core + NAS100 + Pass Accelerator")
    print(f"  Simulations: {N_SIMS:,} per scenario")
    print("=" * 70)

    cfg = load_config(CONFIG_PATH)
    with open(PROFILES_PATH) as f:
        profiles = yaml.safe_load(f)

    inst_profiles = profiles["instruments"]
    challenge_cfg = profiles["modes"]["challenge"]
    funded_cfg = profiles["modes"]["funded"]

    core_signals, throughput_signals = build_signal_pools()
    combined_signals = core_signals + throughput_signals

    print(f"\n  Core pool:        {len(core_signals)} trades (5yr)")
    print(f"  Throughput pool:  {len(throughput_signals)} trades (5yr)")
    print(f"  Combined pool:    {len(combined_signals)} trades (5yr)")

    core_pnl = np.array([s["pnl_r"] for s in core_signals])
    thru_pnl = np.array([s["pnl_r"] for s in throughput_signals])
    comb_pnl = np.array([s["pnl_r"] for s in combined_signals])
    print(f"  Core exp:         {core_pnl.mean():+.3f}R")
    print(f"  Throughput exp:   {thru_pnl.mean():+.3f}R")
    print(f"  Combined exp:     {comb_pnl.mean():+.3f}R")

    # ── Scenario A: Core only ────────────────────────────────
    ch_a = simulate_challenge(core_signals, challenge_cfg, inst_profiles, use_accelerator=False)
    fund_a = simulate_funded(core_signals, funded_cfg, inst_profiles)
    print_results("SCENARIO A: Core Only (XAU + GBP + JPY)", ch_a, fund_a)

    # ── Scenario B: Core + NAS100 ────────────────────────────
    ch_b = simulate_challenge(combined_signals, challenge_cfg, inst_profiles, use_accelerator=False)
    fund_b_core = simulate_funded(core_signals, funded_cfg, inst_profiles)
    print_results("SCENARIO B: Core + NAS100 (no accelerator)", ch_b, fund_b_core)

    # ── Scenario C: Core + NAS100 + Accelerator ──────────────
    ch_c = simulate_challenge(combined_signals, challenge_cfg, inst_profiles, use_accelerator=True)
    fund_c_core = simulate_funded(core_signals, funded_cfg, inst_profiles)
    print_results("SCENARIO C: Core + NAS100 + Pass Accelerator", ch_c, fund_c_core)

    # ── Comparison Table ─────────────────────────────────────
    print("\n" + "=" * 70)
    print("  HEAD-TO-HEAD COMPARISON")
    print("=" * 70)
    header = f"  {'Metric':<25s} {'A:Core':<15s} {'B:+NAS100':<15s} {'C:+Accel':<15s}"
    print(header)
    print("  " + "-" * 65)

    for label, key, fmt in [
        ("Pass rate", "pass_rate", "{:.1f}%"),
        ("Avg pass day", "avg_pass_day", "{:.0f}"),
        ("Avg final eq", "avg_eq", "{:+.1f}%"),
        ("Avg max DD", "avg_dd", "{:.1f}%"),
        ("Failed DD", "failed_dd", "{:,}"),
        ("Failed timeout", "failed_timeout", "{:,}"),
    ]:
        va = fmt.format(ch_a[key])
        vb = fmt.format(ch_b[key])
        vc = fmt.format(ch_c[key])
        print(f"  {label:<25s} {va:<15s} {vb:<15s} {vc:<15s}")

    # Delta analysis
    print(f"\n  INCREMENTAL VALUE:")
    print(f"    NAS100 throughput:     {ch_b['pass_rate'] - ch_a['pass_rate']:+.1f}pp pass rate")
    print(f"    Pass accelerator:      {ch_c['pass_rate'] - ch_b['pass_rate']:+.1f}pp on top")
    print(f"    Total vs core only:    {ch_c['pass_rate'] - ch_a['pass_rate']:+.1f}pp")

    if ch_c["pass_rate"] > 0:
        total_uplift = ch_c["pass_rate"] / max(ch_a["pass_rate"], 0.1)
        print(f"    Total multiplier:      {total_uplift:.1f}x")

    # Funded comparison (core only for all — NAS100 excluded from funded)
    print(f"\n  FUNDED (Core book only — NAS100 excluded):")
    print(f"    Avg monthly:      {fund_a['avg_monthly']:+.2f}%")
    print(f"    Positive months:  {fund_a['positive_months_pct']:.0f}%")
    print(f"    Blown rate:       {fund_a['blown_pct']:.1f}%")

    # Final verdict
    print("\n" + "=" * 70)
    print("  VERDICT")
    print("=" * 70)
    best = max([(ch_a["pass_rate"], "A"), (ch_b["pass_rate"], "B"), (ch_c["pass_rate"], "C")])
    print(f"  Best challenge config:   Scenario {best[1]} ({best[0]:.1f}% pass rate)")
    print(f"  Funded recommendation:   Core only (stable, NAS100 excluded)")

    # Key question answered
    nas_contribution = ch_b["pass_rate"] - ch_a["pass_rate"]
    accel_contribution = ch_c["pass_rate"] - ch_b["pass_rate"]
    if nas_contribution > accel_contribution:
        print(f"  Primary FTMO driver:     NAS100 throughput (+{nas_contribution:.1f}pp)")
    else:
        print(f"  Primary FTMO driver:     Pass accelerator (+{accel_contribution:.1f}pp)")

    print("=" * 70)


if __name__ == "__main__":
    main()
