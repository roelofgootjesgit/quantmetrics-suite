"""Unit tests for backtest engine and metrics."""
import numpy as np
import pandas as pd
import pytest
from datetime import datetime, timedelta

from src.quantbuild.models.trade import Trade, calculate_rr
from src.quantbuild.backtest.metrics import compute_metrics, compute_metrics_by_direction, compute_full_report
from src.quantbuild.backtest.engine import _simulate_trade, _prepare_sim_cache


def _make_ohlcv(n=200, base=2000.0, seed=42):
    rng = np.random.RandomState(seed)
    dates = pd.date_range("2025-01-01", periods=n, freq="15min", tz="UTC")
    close = base + np.cumsum(rng.randn(n) * 2)
    high = close + rng.uniform(0.5, 3.0, n)
    low = close - rng.uniform(0.5, 3.0, n)
    return pd.DataFrame({"open": close + rng.randn(n)*0.5, "high": high, "low": low, "close": close, "volume": rng.randint(100,1000,n)}, index=dates)


def _make_trades(n=10):
    trades = []
    base_time = datetime(2025, 1, 1, 10, 0)
    for i in range(n):
        is_win = i % 3 != 0
        trades.append(Trade(
            timestamp_open=base_time + timedelta(hours=i),
            timestamp_close=base_time + timedelta(hours=i, minutes=45),
            symbol="XAUUSD", direction="LONG" if i % 2 == 0 else "SHORT",
            entry_price=2000.0, exit_price=2004.0 if is_win else 1998.0,
            sl=1998.0, tp=2004.0,
            profit_usd=4.0 if is_win else -2.0, profit_r=2.0 if is_win else -1.0,
            result="WIN" if is_win else "LOSS", regime="TRENDING" if i < 5 else "RANGING",
        ))
    return trades


class TestMetrics:
    def test_empty(self):
        assert compute_metrics([])["trade_count"] == 0

    def test_basic(self):
        m = compute_metrics(_make_trades(10))
        assert m["trade_count"] == 10
        assert 0 <= m["win_rate"] <= 100

    def test_by_direction(self):
        by_dir = compute_metrics_by_direction(_make_trades(10))
        assert "LONG" in by_dir and "SHORT" in by_dir

    def test_full_report(self):
        report = compute_full_report(_make_trades(10))
        assert all(k in report for k in ["overall", "by_direction", "by_regime", "by_session"])


class TestSimulateTrade:
    def test_trade_produces_result(self):
        df = _make_ohlcv(200)
        cache = _prepare_sim_cache(df)
        result = _simulate_trade(df, 50, "LONG", 2.0, 1.0, _cache=cache)
        assert result["result"] in ("WIN", "LOSS", "TIMEOUT")
        assert result["entry_price"] > 0

    def test_cache_consistency(self):
        df = _make_ohlcv(200)
        cache = _prepare_sim_cache(df)
        r1 = _simulate_trade(df, 50, "LONG", 2.0, 1.0, _cache=cache)
        r2 = _simulate_trade(df, 50, "LONG", 2.0, 1.0, _cache=None)
        assert r1["result"] == r2["result"]
        assert r1["entry_price"] == pytest.approx(r2["entry_price"])
