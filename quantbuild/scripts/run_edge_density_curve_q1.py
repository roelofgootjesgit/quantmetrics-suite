#!/usr/bin/env python3
"""Sprint 2 — Edge density curve: run ladder configs + print CSV-ready metrics.

Gebruikt hetzelfde Q1-venster als configs/backtest_2026_jan_mar*. Run vanaf repo root::

    python scripts/run_edge_density_curve_q1.py

Dependencies: lokale data/market_cache zoals bij normale backtest.
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.quantbuild.backtest.engine import run_backtest
from src.quantbuild.config import load_config
from src.quantbuild.models.trade import Trade


RUNS: list[tuple[str, str]] = [
    ("v00_expansion_ny_strict", "configs/backtest_2026_jan_mar_expansion_ny.yaml"),
    ("v01_h1_off", "configs/backtest_2026_jan_mar_expansion_ny_curve_v01.yaml"),
    ("v02_h1_cooldown_off", "configs/backtest_2026_jan_mar_expansion_ny_curve_v02.yaml"),
    ("v03_pos_limit_off", "configs/backtest_2026_jan_mar_expansion_ny_curve_v03.yaml"),
    ("v04_session_off", "configs/backtest_2026_jan_mar_expansion_ny_curve_v04.yaml"),
    ("v05_research_raw_first", "configs/backtest_2026_jan_mar_expansion_ny_curve_v05.yaml"),
    ("ceiling_edge_discovery", "configs/backtest_2026_jan_mar_edge_discovery.yaml"),
]


def _max_dd_r(trades: list[Trade]) -> float:
    """Max drawdown in R-units from cumulative realised R."""
    cum = 0.0
    peak = 0.0
    max_dd = 0.0
    for t in trades:
        cum += float(t.profit_r)
        peak = max(peak, cum)
        max_dd = min(max_dd, cum - peak)
    return float(max_dd)


def _metrics(label: str, trades: list[Trade]) -> dict[str, float | int | str]:
    n = len(trades)
    if n == 0:
        return {
            "label": label,
            "n": 0,
            "mean_r": 0.0,
            "sum_r": 0.0,
            "winrate_pct": 0.0,
            "max_dd_r": 0.0,
            "pf_like": 0.0,
        }
    rs = [float(t.profit_r) for t in trades]
    wins = sum(1 for t in trades if str(t.result.value) == "WIN")
    losses = sum(1 for t in trades if str(t.result.value) == "LOSS")
    sum_pos = sum(r for r in rs if r > 0)
    sum_neg = abs(sum(r for r in rs if r < 0))
    pf = (sum_pos / sum_neg) if sum_neg > 1e-9 else (999.99 if sum_pos > 0 else 0.0)
    return {
        "label": label,
        "n": n,
        "mean_r": sum(rs) / n,
        "sum_r": sum(rs),
        "winrate_pct": 100.0 * wins / n,
        "max_dd_r": _max_dd_r(trades),
        "pf_like": pf,
    }


def main() -> int:
    rows: list[dict[str, float | int | str]] = []
    for label, rel in RUNS:
        cfg_path = ROOT / rel
        cfg = load_config(cfg_path)
        trades = run_backtest(cfg)
        row = _metrics(label, trades)
        rows.append(row)
        print(
            f"{label:28} n={row['n']:3}  mean_r={row['mean_r']:7.3f}  sum_r={row['sum_r']:8.2f}  "
            f"WR={row['winrate_pct']:5.1f}%  maxDD_r={row['max_dd_r']:7.2f}  PF~{row['pf_like']:5.2f}"
        )

    out = ROOT / "output_rapport" / "edge_density_curve_q1_2026.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["label", "n", "mean_r", "sum_r", "winrate_pct", "max_dd_r", "pf_like"],
        )
        w.writeheader()
        for r in rows:
            w.writerow(r)
    print(f"\nCSV written: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
