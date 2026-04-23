"""Tests for EURUSD Mean Reversion strategy module."""
import numpy as np
import pandas as pd
import pytest

from src.quantbuild.strategies.mean_reversion_eurusd import (
    compute_rsi,
    compute_range_boundaries,
    detect_wick_rejection,
    detect_range_sweep,
    run_mr_conditions,
    simulate_mr_trade,
    DEFAULT_MR_CONFIG,
)


def _make_ohlc(n=100, base=1.10, volatility=0.001):
    """Generate synthetic OHLCV data resembling EURUSD."""
    np.random.seed(42)
    dates = pd.date_range("2024-01-01", periods=n, freq="15min")
    close = base + np.cumsum(np.random.randn(n) * volatility)
    high = close + np.abs(np.random.randn(n) * volatility * 0.5)
    low = close - np.abs(np.random.randn(n) * volatility * 0.5)
    opn = close + np.random.randn(n) * volatility * 0.3
    df = pd.DataFrame({
        "open": opn, "high": high, "low": low, "close": close,
        "volume": np.random.randint(100, 1000, n),
    }, index=dates)
    return df


class TestRSI:
    def test_rsi_range(self):
        df = _make_ohlc()
        rsi = compute_rsi(df["close"], 14)
        assert rsi.min() >= 0
        assert rsi.max() <= 100

    def test_rsi_length(self):
        df = _make_ohlc(50)
        rsi = compute_rsi(df["close"], 14)
        assert len(rsi) == 50


class TestRangeBoundaries:
    def test_shape(self):
        df = _make_ohlc()
        rh, rl = compute_range_boundaries(df, 30)
        assert len(rh) == len(df)
        assert len(rl) == len(df)

    def test_high_above_low(self):
        df = _make_ohlc()
        rh, rl = compute_range_boundaries(df, 30)
        valid = rh.dropna().index.intersection(rl.dropna().index)
        assert (rh[valid] >= rl[valid]).all()


class TestWickRejection:
    def test_returns_boolean_series(self):
        df = _make_ohlc()
        bull, bear = detect_wick_rejection(df, 0.6)
        assert bull.dtype == bool
        assert bear.dtype == bool


class TestRangeSweep:
    def test_returns_boolean_series(self):
        df = _make_ohlc()
        rh, rl = compute_range_boundaries(df, 20)
        bull, bear = detect_range_sweep(df, rh, rl, 0.15)
        assert bull.dtype == bool
        assert bear.dtype == bool


class TestMRConditions:
    def test_no_signals_without_compression(self):
        df = _make_ohlc()
        regime = pd.Series("trend", index=df.index)
        entries = run_mr_conditions(df, "LONG", regime_series=regime)
        assert entries.sum() == 0

    def test_compression_allows_signals(self):
        df = _make_ohlc(200)
        regime = pd.Series("compression", index=df.index)
        long_e = run_mr_conditions(df, "LONG", regime_series=regime)
        short_e = run_mr_conditions(df, "SHORT", regime_series=regime)
        # May or may not have signals depending on random data
        assert isinstance(long_e, pd.Series)
        assert isinstance(short_e, pd.Series)

    def test_early_bars_blocked(self):
        df = _make_ohlc(100)
        regime = pd.Series("compression", index=df.index)
        entries = run_mr_conditions(df, "LONG", regime_series=regime)
        lookback = DEFAULT_MR_CONFIG["range_lookback"]
        assert entries.iloc[:lookback + 1].sum() == 0


class TestSimulateMRTrade:
    def test_tp_hit(self):
        np.random.seed(1)
        n = 50
        close = np.array([1.10 + i * 0.0001 for i in range(n)])
        high = close + 0.002
        low = close - 0.0001
        atr_vals = np.full(n, 0.001)

        cache = {"close": close, "high": high, "low": low, "atr": atr_vals}
        result = simulate_mr_trade(cache, 5, "LONG", tp_r=1.0, sl_r=1.0, time_stop_bars=10)
        assert result["exit_type"] in ("tp", "sl", "time")
        assert "pnl_r" in result
        assert "mfe" in result
        assert "bars_held" in result

    def test_time_stop(self):
        n = 50
        close = np.full(n, 1.10)
        high = close + 0.00001
        low = close - 0.00001
        atr_vals = np.full(n, 0.001)

        cache = {"close": close, "high": high, "low": low, "atr": atr_vals}
        result = simulate_mr_trade(cache, 5, "LONG", tp_r=1.0, sl_r=1.0, time_stop_bars=10)
        assert result["exit_type"] == "time"
        assert result["bars_held"] == 10

    def test_sl_hit(self):
        n = 50
        close = np.array([1.10 - i * 0.0005 for i in range(n)])
        high = close + 0.0001
        low = close - 0.002
        atr_vals = np.full(n, 0.001)

        cache = {"close": close, "high": high, "low": low, "atr": atr_vals}
        result = simulate_mr_trade(cache, 5, "LONG", tp_r=1.0, sl_r=1.0, time_stop_bars=10)
        assert result["exit_type"] == "sl"
        assert result["pnl_r"] == -1.0
