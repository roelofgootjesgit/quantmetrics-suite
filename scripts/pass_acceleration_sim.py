"""
Pass Acceleration Simulation — FTMO Challenge optimizer with phase-based risk.

Combines:
  - Existing portfolio signals (XAUUSD, GBPUSD, USDJPY)
  - AdaptiveModeLayer
  - PortfolioHeatEngine
  - PassAccelerator (ATTACK / NORMAL / SECURE / COAST)

Compares: Standard adaptive vs Accelerated challenge runs
via Monte Carlo simulation.

Usage:
    python scripts/pass_acceleration_sim.py
"""
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import yaml

from src.quantbuild.config import load_config
from src.quantbuild.logging_config import setup_logging
from src.quantbuild.execution.adaptive_mode import AdaptiveModeLayer
from src.quantbuild.execution.portfolio_heat import PortfolioHeatEngine
from src.quantbuild.execution.pass_accelerator import PassAccelerator

CONFIG_PATH = "configs/strict_prod_v2.yaml"
PROFILES_PATH = "configs/instruments/instrument_profiles.yaml"

# FTMO challenge params
CHALLENGE_DAYS = 30
N_SIMULATIONS = 10_000


def load_signals():
    """Load cached signals from portfolio_adaptive_sim or generate synthetic ones from historical stats."""
    signal_cache = Path("reports/latest/portfolio_signals.json")
    if signal_cache.exists():
        import json
        with open(signal_cache) as f:
            data = json.load(f)
        return data

    # Fallback: generate from validated historical distributions
    np.random.seed(42)
    signals = []

    # XAUUSD: ~69 trades/5yr, exp ~0.32R, WR ~42%, mostly TREND
    for _ in range(69):
        pnl = np.random.choice(
            [2.0, 1.5, 1.0, 0.5, -1.0],
            p=[0.20, 0.12, 0.10, 0.05, 0.53]
        )
        signals.append({
            "symbol": "XAUUSD", "pnl_r": float(pnl),
            "regime": np.random.choice(["trend", "expansion"], p=[0.75, 0.25]),
            "asset_class": "metals",
        })

    # GBPUSD: ~6 trades/5yr, exp ~0.60R (TREND only)
    for _ in range(6):
        pnl = np.random.choice([2.0, 1.5, -1.0], p=[0.40, 0.20, 0.40])
        signals.append({
            "symbol": "GBPUSD", "pnl_r": float(pnl),
            "regime": "trend", "asset_class": "fx_major",
        })

    # USDJPY: ~4 trades/5yr, exp ~0.33R
    for _ in range(4):
        pnl = np.random.choice([2.0, 1.0, -1.0], p=[0.35, 0.15, 0.50])
        signals.append({
            "symbol": "USDJPY", "pnl_r": float(pnl),
            "regime": "trend", "asset_class": "fx_major",
        })

    np.random.shuffle(signals)
    return signals


def simulate_ftmo_challenge(
    pnl_pool,
    symbol_pool,
    asset_pool,
    regime_pool,
    mode_config,
    use_accelerator=False,
    n_sims=N_SIMULATIONS,
    n_days=CHALLENGE_DAYS,
):
    """Monte Carlo simulation of FTMO challenge with optional pass acceleration."""
    target_pct = mode_config.get("target_pct", 10.0)
    max_daily_dd = mode_config.get("max_daily_loss_pct", 5.0)
    max_total_dd = mode_config.get("max_total_dd_pct", 10.0)
    base_risk = mode_config.get("risk_per_trade_pct", 1.5)

    avg_trades_per_day = len(pnl_pool) / (5 * 250)  # 5yr * 250 trading days

    results = {
        "passed": 0,
        "failed_dd": 0,
        "failed_timeout": 0,
        "pass_days": [],
        "final_equity": [],
        "max_dd_all": [],
        "phase_distribution": {"ATTACK": 0, "NORMAL": 0, "SECURE": 0, "COAST": 0},
    }

    for _ in range(n_sims):
        # Create fresh engines
        heat_config = {
            "portfolio_heat": {
                "max_portfolio_heat_pct": mode_config.get("max_portfolio_heat_pct", 6.0),
                "max_instrument_heat_pct": 3.0,
                "max_correlated_exposure": mode_config.get("max_correlated_exposure", 2),
            }
        }
        heat = PortfolioHeatEngine(heat_config)

        adapt_config = {
            "adaptive_mode": {
                "aggressive_dd_max": 1.5,
                "defensive_dd": 3.0,
                "lockdown_dd": max_total_dd * 0.8,
            }
        }
        adapt = AdaptiveModeLayer(adapt_config)

        accel = None
        if use_accelerator:
            accel_config = {
                "pass_accelerator": {
                    "target_pct": target_pct,
                    "max_daily_loss_pct": max_daily_dd,
                    "max_total_dd_pct": max_total_dd,
                    "challenge_days": n_days,
                    "attack_until_day": 10,
                    "secure_at_pct": target_pct * 0.7,
                    "coast_at_pct": target_pct * 0.9,
                    "dd_danger_zone_pct": max_total_dd * 0.3,
                }
            }
            accel = PassAccelerator(accel_config)
            accel.start_challenge()

        equity = 0.0
        peak = 0.0
        passed = False
        day_of_pass = n_days
        max_dd_sim = 0.0
        sim_phases = {"ATTACK": 0, "NORMAL": 0, "SECURE": 0, "COAST": 0}

        for day in range(1, n_days + 1):
            daily_pnl = 0.0

            # Decide how many trades today (Poisson around historical average)
            # Accelerator can boost this
            base_trades_today = max(0, np.random.poisson(avg_trades_per_day * 1.5))
            if use_accelerator:
                accel.update(equity, day)
                phase = accel.phase
                sim_phases[phase] = sim_phases.get(phase, 0) + 1
                if phase == "ATTACK":
                    base_trades_today = max(base_trades_today, np.random.poisson(avg_trades_per_day * 2.5))
                elif phase == "COAST":
                    base_trades_today = min(base_trades_today, 1)

            for _ in range(base_trades_today):
                idx = np.random.randint(0, len(pnl_pool))
                raw_pnl = pnl_pool[idx]
                sym = symbol_pool[idx]
                asset = asset_pool[idx]
                regime = regime_pool[idx]

                risk_mult = adapt.risk_multiplier
                if use_accelerator:
                    risk_mult = accel.get_effective_risk(1.0, adapt.risk_multiplier)

                effective_risk = base_risk * risk_mult
                trade_pnl_pct = raw_pnl * effective_risk

                # Slippage
                trade_pnl_pct -= 0.065 * effective_risk

                daily_pnl += trade_pnl_pct
                equity += trade_pnl_pct

                adapt.update_equity(equity)
                adapt.record_trade(raw_pnl, symbol=sym, regime=regime)

                if use_accelerator:
                    accel.record_trade(str(day))
                    accel.update(equity, day)

                peak = max(peak, equity)
                dd = peak - equity
                max_dd_sim = max(max_dd_sim, dd)

            # Check daily DD
            if abs(daily_pnl) >= max_daily_dd:
                results["failed_dd"] += 1
                break

            # Check total DD
            if max_dd_sim >= max_total_dd:
                results["failed_dd"] += 1
                break

            # Check pass
            if equity >= target_pct:
                results["passed"] += 1
                day_of_pass = day
                passed = True
                break
        else:
            if not passed:
                results["failed_timeout"] += 1

        results["pass_days"].append(day_of_pass)
        results["final_equity"].append(equity)
        results["max_dd_all"].append(max_dd_sim)

        for p, c in sim_phases.items():
            results["phase_distribution"][p] = results["phase_distribution"].get(p, 0) + c

    results["pass_rate"] = 100 * results["passed"] / n_sims
    results["avg_pass_day"] = float(np.mean([d for d in results["pass_days"] if d < n_days])) if results["passed"] else 0
    results["avg_final_eq"] = float(np.mean(results["final_equity"]))
    results["avg_max_dd"] = float(np.mean(results["max_dd_all"]))
    results["ev_per_attempt"] = float(np.mean(results["final_equity"])) * 100  # assume $100k account

    return results


def main():
    print("=" * 70)
    print("  PASS ACCELERATION SIMULATION")
    print("  FTMO Challenge: Standard vs Accelerated")
    print("=" * 70)

    cfg = load_config(CONFIG_PATH)
    setup_logging(cfg)

    with open(PROFILES_PATH) as f:
        profiles = yaml.safe_load(f)

    mode_config = profiles["modes"]["challenge"]
    signals = load_signals()
    pnl_pool = np.array([s["pnl_r"] for s in signals])
    symbol_pool = [s.get("symbol", "XAUUSD") for s in signals]
    asset_pool = [s.get("asset_class", "metals") for s in signals]
    regime_pool = [s.get("regime", "trend") for s in signals]

    print(f"\n  Signal pool: {len(signals)} trades")
    print(f"  Pool expectancy: {pnl_pool.mean():+.3f}R")
    print(f"  Pool WR: {100 * (pnl_pool > 0).mean():.0f}%")
    print(f"  Simulations: {N_SIMULATIONS:,}")

    # Standard adaptive (no acceleration)
    print("\n" + "-" * 70)
    print("  [A] STANDARD ADAPTIVE (no acceleration)")
    print("-" * 70)
    std = simulate_ftmo_challenge(
        pnl_pool, symbol_pool, asset_pool, regime_pool,
        mode_config, use_accelerator=False,
    )
    print(f"  Pass rate:     {std['pass_rate']:.1f}%")
    print(f"  Avg pass day:  {std['avg_pass_day']:.0f}")
    print(f"  Avg final eq:  {std['avg_final_eq']:+.1f}%")
    print(f"  Avg max DD:    {std['avg_max_dd']:.1f}%")
    print(f"  EV / attempt:  ${std['ev_per_attempt']:+,.0f}")
    print(f"  Failed DD:     {std['failed_dd']}")
    print(f"  Failed timeout:{std['failed_timeout']}")

    # With pass acceleration
    print("\n" + "-" * 70)
    print("  [B] PASS ACCELERATOR (phase-based risk)")
    print("-" * 70)
    acc = simulate_ftmo_challenge(
        pnl_pool, symbol_pool, asset_pool, regime_pool,
        mode_config, use_accelerator=True,
    )
    print(f"  Pass rate:     {acc['pass_rate']:.1f}%")
    print(f"  Avg pass day:  {acc['avg_pass_day']:.0f}")
    print(f"  Avg final eq:  {acc['avg_final_eq']:+.1f}%")
    print(f"  Avg max DD:    {acc['avg_max_dd']:.1f}%")
    print(f"  EV / attempt:  ${acc['ev_per_attempt']:+,.0f}")
    print(f"  Failed DD:     {acc['failed_dd']}")
    print(f"  Failed timeout:{acc['failed_timeout']}")

    # Phase distribution
    total_phases = sum(acc["phase_distribution"].values()) or 1
    print(f"\n  Phase distribution:")
    for p in ["ATTACK", "NORMAL", "SECURE", "COAST"]:
        pct = 100 * acc["phase_distribution"].get(p, 0) / total_phases
        print(f"    {p:<10s}: {pct:5.1f}%")

    # Comparison
    print("\n" + "=" * 70)
    print("  COMPARISON")
    print("=" * 70)
    delta_pass = acc["pass_rate"] - std["pass_rate"]
    delta_days = acc["avg_pass_day"] - std["avg_pass_day"] if std["avg_pass_day"] > 0 else 0
    delta_dd = acc["avg_max_dd"] - std["avg_max_dd"]

    print(f"  Pass rate delta:  {delta_pass:+.1f}pp  ({'better' if delta_pass > 0 else 'worse'})")
    print(f"  Pass speed delta: {delta_days:+.0f} days  ({'faster' if delta_days < 0 else 'slower'})")
    print(f"  DD delta:         {delta_dd:+.1f}pp  ({'more' if delta_dd > 0 else 'less'} risk)")
    print(f"  EV delta:         ${acc['ev_per_attempt'] - std['ev_per_attempt']:+,.0f}")

    # Business case
    print("\n" + "=" * 70)
    print("  FTMO BUSINESS CASE")
    print("=" * 70)
    attempt_cost = 155  # FTMO $100k challenge cost
    pass_rate_acc = acc["pass_rate"] / 100
    ev_per_attempt = acc["ev_per_attempt"]
    payout_split = 0.80

    expected_payout = (pass_rate_acc * 10_000 * payout_split)
    expected_cost = attempt_cost
    net_ev = expected_payout - expected_cost

    print(f"  Challenge cost:       ${attempt_cost}")
    print(f"  Pass rate:            {acc['pass_rate']:.1f}%")
    print(f"  Expected payout/pass: ${10_000 * payout_split:,.0f} (80% split)")
    print(f"  Net EV per attempt:   ${net_ev:+,.0f}")
    print(f"  Attempts to 1 pass:   {1 / pass_rate_acc:.1f}" if pass_rate_acc > 0 else "  N/A")
    print(f"  Avg cost to 1 pass:   ${attempt_cost / pass_rate_acc:,.0f}" if pass_rate_acc > 0 else "  N/A")

    print("\n" + "=" * 70)
    print("  Done.")
    print("=" * 70)


if __name__ == "__main__":
    main()
