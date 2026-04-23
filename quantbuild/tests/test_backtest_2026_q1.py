"""Q1 2026 backtest slice: config merge + engine smoke (mocked OHLC)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.quantbuild.backtest.engine import run_backtest
from src.quantbuild.config import load_config, quantbuild_repo_root


def _make_ohlcv_15m(*, start: str, periods: int, seed: int = 7) -> pd.DataFrame:
    rng = np.random.RandomState(seed)
    dates = pd.date_range(start, periods=periods, freq="15min", tz="UTC")
    close = 2650.0 + np.cumsum(rng.randn(periods) * 1.5)
    high = close + rng.uniform(0.3, 2.0, periods)
    low = close - rng.uniform(0.3, 2.0, periods)
    return pd.DataFrame(
        {
            "open": close + rng.randn(periods) * 0.2,
            "high": high,
            "low": low,
            "close": close,
            "volume": rng.randint(50, 500, periods),
        },
        index=dates,
    )


class TestBacktest2026Q1Config:
    """``configs/backtest_2026_jan_mar.yaml`` — UTC window Jan–Mar 2026 + strict_prod_v2 merge."""

    def test_yaml_loads_window_and_merges_strategy(self) -> None:
        root = quantbuild_repo_root()
        path = root / "configs" / "backtest_2026_jan_mar.yaml"
        assert path.is_file(), f"missing {path}"
        cfg = load_config(str(path))
        bt = cfg.get("backtest") or {}
        assert bt.get("start_date") == "2026-01-01"
        assert bt.get("end_date") == "2026-03-31"
        assert cfg.get("symbol") == "XAUUSD"
        assert cfg.get("quantlog", {}).get("enabled") is True
        strat = cfg.get("strategy") or {}
        assert strat.get("name") == "sqe_xauusd"
        assert "trend_context" in strat


class TestBacktest2026Q1EngineSmoke:
    """Minimal engine run for Q1 window: no network, isolated quantlog dir."""

    def test_run_backtest_q1_2026_window_completes(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        import src.quantbuild.backtest.engine as eng

        root = quantbuild_repo_root()
        cfg = load_config(str(root / "configs" / "backtest_2026_jan_mar.yaml"))
        ql_dir = tmp_path / "quantlog_q1_2026"
        cfg["data"] = {"base_path": str(tmp_path / "market_cache")}
        cfg["quantlog"] = {
            **(cfg.get("quantlog") or {}),
            "enabled": True,
            "base_path": str(ql_dir),
            "environment": "backtest",
            "run_id": "pytest_bt_2026_q1",
            "session_id": "pytest_bt_2026_q1_sess",
            "consolidated_run_file": True,
            "auto_analytics": False,
        }

        # Span before/after Q1 2026 so fixed-window slice is non-empty
        df_15m = _make_ohlcv_15m(start="2025-11-01", periods=14000)

        def fake_load_parquet(base_path, symbol, timeframe, start=None, end=None):
            if timeframe == "15m":
                return df_15m
            if timeframe == "1h":
                return pd.DataFrame()
            return pd.DataFrame()

        # One LONG candidate inside Q1 2026 so QuantLog emits and consolidated file is created
        q1_ts = pd.Timestamp("2026-02-10 14:00:00", tz="UTC")
        pos = int(df_15m.index.get_indexer([q1_ts], method="nearest")[0])

        def fake_run_sqe(data, direction, sqe_cfg, _precomputed_df=None):
            out = pd.Series(False, index=data.index)
            if direction == "LONG" and 0 <= pos < len(out):
                out.iloc[pos] = True
            return out

        monkeypatch.setattr(eng, "load_parquet", fake_load_parquet)
        monkeypatch.setattr(eng, "ensure_data", lambda **kwargs: df_15m)
        monkeypatch.setattr(eng, "run_sqe_conditions", fake_run_sqe)

        trades = run_backtest(cfg)
        assert isinstance(trades, list)
        jsonl = ql_dir / "runs" / "pytest_bt_2026_q1.jsonl"
        assert jsonl.is_file(), "QuantLog consolidated JSONL should exist for this backtest"
        assert jsonl.stat().st_size > 0
