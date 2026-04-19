"""
Export cumulative R equity curve from a backtest run to PNG (README / showcase).

Uses the same long-backtest risk overrides as `strategy_variants_backtest.py`
(equity kill switch / daily loss caps disabled for simulation).

If `ensure_data` already has >100 bars but only a short calendar range (stale cache),
delete `data/market_cache/<SYMBOL>/*.parquet` and re-fetch before exporting.

Examples:
  python scripts/export_equity_chart.py -c configs/strict_prod_v2.yaml
  python scripts/export_equity_chart.py -c configs/strict_prod_v2.yaml --days 365
"""
from __future__ import annotations

import argparse
import copy
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _backtest_risk_overrides(cfg: dict, max_tps: int = 3) -> dict:
    cfg = copy.deepcopy(cfg)
    cfg.setdefault("risk", {})
    cfg["risk"]["equity_kill_switch_pct"] = 999.0
    cfg["risk"]["max_daily_loss_r"] = 999.0
    cfg["risk"]["max_trades_per_session"] = max_tps
    return cfg


def main() -> int:
    parser = argparse.ArgumentParser(description="Export backtest equity curve (cumulative R) to PNG")
    parser.add_argument("-c", "--config", required=True, help="YAML config path")
    parser.add_argument(
        "-o",
        "--output",
        default=str(REPO_ROOT / "docs" / "assets" / "equity_curve_5y.png"),
        help="Output PNG path",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=None,
        help="Override backtest.default_period_days (default: from YAML)",
    )
    parser.add_argument(
        "--no-sibling-copy",
        action="store_true",
        help="Do not copy PNG to sibling QuantOS checkout ../quantmetrics_os/docs/assets/ if that folder exists",
    )
    args = parser.parse_args()

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.dates as mdates
    import matplotlib.pyplot as plt

    from src.quantbuild.backtest.engine import run_backtest
    from src.quantbuild.config import load_config
    from src.quantbuild.logging_config import setup_logging

    cfg = load_config(args.config)
    cfg = _backtest_risk_overrides(cfg)
    if args.days is not None:
        cfg.setdefault("backtest", {})["default_period_days"] = args.days

    setup_logging(cfg)
    trades = run_backtest(cfg)
    if not trades:
        print("No trades; nothing to plot.", file=sys.stderr)
        return 1

    times = [t.timestamp_close for t in trades]
    cum_r = []
    s = 0.0
    for t in trades:
        s += t.profit_r
        cum_r.append(s)

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=(11, 5), dpi=140)
    ax.plot(times, cum_r, color="#047857", linewidth=1.4, label="Cumulative R")
    ax.fill_between(times, cum_r, alpha=0.12, color="#047857")
    ax.axhline(0, color="#94a3b8", linewidth=0.8, linestyle="--")
    ax.set_title("QuantBuild — Signal Engine — backtest equity (cumulative R)", fontsize=13, fontweight="600", color="#0f172a")
    ax.set_xlabel("Date (UTC)")
    ax.set_ylabel("Cumulative R")
    ax.grid(True, alpha=0.25)
    ax.legend(loc="upper left", framealpha=0.9)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(out, format="png", facecolor="#f8fafc", edgecolor="none")
    plt.close(fig)

    print(f"Wrote {out} ({len(trades)} trades, final R={cum_r[-1]:.2f})")

    if not args.no_sibling_copy:
        sibling = REPO_ROOT.parent / "quantmetrics_os" / "docs" / "assets"
        if sibling.is_dir():
            twin = sibling / out.name
            twin.write_bytes(out.read_bytes())
            print(f"Copied to {twin}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
