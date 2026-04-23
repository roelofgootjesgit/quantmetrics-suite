"""A/B test: pure ICT strategy vs ICT + news layer.

Runs backtest twice:
  A) Standard ICT-only (news disabled)
  B) ICT + news gate/sentiment integration

Compares key metrics.

Usage:
    python scripts/ab_test_news.py --config configs/xauusd.yaml --days 30
"""
import argparse
import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.quantbuild.config import load_config
from src.quantbuild.logging_config import setup_logging
from src.quantbuild.backtest.engine import run_backtest
from src.quantbuild.backtest.metrics import compute_metrics


def main():
    parser = argparse.ArgumentParser(description="A/B test: ICT vs ICT+News")
    parser.add_argument("--config", "-c", default="configs/xauusd.yaml")
    parser.add_argument("--days", "-d", type=int, default=30)
    args = parser.parse_args()

    cfg = load_config(args.config)
    setup_logging(cfg)

    # --- Run A: ICT only (news disabled) ---
    cfg_a = copy.deepcopy(cfg)
    cfg_a["news"] = {"enabled": False}
    cfg_a.setdefault("backtest", {})["default_period_days"] = args.days

    print("=" * 60)
    print("RUN A: ICT-only (news disabled)")
    print("=" * 60)
    trades_a = run_backtest(cfg_a)
    metrics_a = compute_metrics(trades_a)

    # --- Run B: ICT + News ---
    cfg_b = copy.deepcopy(cfg)
    cfg_b.setdefault("news", {})["enabled"] = True
    cfg_b.setdefault("backtest", {})["default_period_days"] = args.days

    print("\n" + "=" * 60)
    print("RUN B: ICT + News layer")
    print("=" * 60)
    trades_b = run_backtest(cfg_b)
    metrics_b = compute_metrics(trades_b)

    # --- Comparison ---
    print("\n" + "=" * 60)
    print("A/B COMPARISON")
    print("=" * 60)

    keys = ["trade_count", "win_rate", "profit_factor", "net_pnl", "max_drawdown", "expectancy_r"]
    print(f"{'Metric':<20} {'ICT-only':>12} {'ICT+News':>12} {'Delta':>12}")
    print("-" * 60)
    for k in keys:
        a_val = metrics_a.get(k, 0)
        b_val = metrics_b.get(k, 0)
        delta = b_val - a_val
        print(f"{k:<20} {a_val:>12.2f} {b_val:>12.2f} {delta:>+12.2f}")

    # Save results
    results = {
        "ict_only": metrics_a,
        "ict_plus_news": metrics_b,
        "delta": {k: metrics_b.get(k, 0) - metrics_a.get(k, 0) for k in keys},
        "config": {"days": args.days},
    }
    out_dir = Path("reports/latest")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "ab_test_news.json"
    out_path.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"\nResults saved to {out_path}")


if __name__ == "__main__":
    main()
