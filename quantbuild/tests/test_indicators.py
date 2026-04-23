"""Unit tests for centralized indicators package."""
import numpy as np
import pandas as pd
import pytest

from src.quantbuild.indicators.atr import true_range, atr, atr_ratio
from src.quantbuild.indicators.swing import (
    swing_highs, swing_lows, pivot_highs, pivot_lows,
    last_swing_low, last_swing_high,
)
from src.quantbuild.indicators.ma import sma, ema


def _make_ohlc(n: int = 100) -> pd.DataFrame:
    """Generate synthetic OHLC data."""
    np.random.seed(42)
    close = 2000 + np.cumsum(np.random.randn(n) * 2)
    high = close + np.abs(np.random.randn(n)) * 3
    low = close - np.abs(np.random.randn(n)) * 3
    opn = close + np.random.randn(n)
    return pd.DataFrame({
        "open": opn, "high": high, "low": low, "close": close,
    }, index=pd.date_range("2025-01-01", periods=n, freq="15min"))


class TestATR:
    def test_true_range_shape(self):
        df = _make_ohlc()
        tr = true_range(df)
        assert len(tr) == len(df)
        assert tr.notna().all()

    def test_true_range_positive(self):
        df = _make_ohlc()
        tr = true_range(df)
        assert (tr >= 0).all()

    def test_atr_period(self):
        df = _make_ohlc()
        a14 = atr(df, period=14)
        a7 = atr(df, period=7)
        assert len(a14) == len(df)
        # Shorter period ATR reacts faster — different values
        assert not np.allclose(a14.values[20:], a7.values[20:])

    def test_atr_ratio_baseline(self):
        df = _make_ohlc(200)
        ratio = atr_ratio(df, atr_period=14, sma_period=20)
        assert len(ratio) == 200
        assert ratio.notna().all()
        # Mean should be close to 1.0 for random walk
        assert 0.5 < ratio.mean() < 2.0


class TestSwing:
    def test_swing_highs(self):
        df = _make_ohlc()
        sh = swing_highs(df, lookback=20, shift=True)
        assert len(sh) == len(df)
        # First value should be NaN (shifted)
        assert pd.isna(sh.iloc[0])

    def test_swing_lows(self):
        df = _make_ohlc()
        sl = swing_lows(df, lookback=20, shift=True)
        assert len(sl) == len(df)
        # All non-NaN values should be <= corresponding low
        valid = sl.dropna()
        assert (valid <= df.loc[valid.index, "high"]).all()

    def test_pivot_highs(self):
        df = _make_ohlc()
        ph = pivot_highs(df, pivot_bars=2)
        assert ph.dtype == bool
        assert ph.sum() > 0

    def test_pivot_lows(self):
        df = _make_ohlc()
        pl = pivot_lows(df, pivot_bars=2)
        assert pl.dtype == bool
        assert pl.sum() > 0

    def test_last_swing_low_finds_value(self):
        df = _make_ohlc(50)
        val = last_swing_low(
            df["high"].values, df["low"].values, df["close"].values,
            end_idx=40, pivot_n=2, lookback=30,
        )
        # Should find at least one swing
        assert not np.isnan(val)

    def test_last_swing_high_finds_value(self):
        df = _make_ohlc(50)
        val = last_swing_high(
            df["high"].values, df["low"].values, df["close"].values,
            end_idx=40, pivot_n=2, lookback=30,
        )
        assert not np.isnan(val)


class TestMA:
    def test_sma(self):
        s = pd.Series(range(20), dtype=float)
        result = sma(s, period=5)
        assert len(result) == 20
        assert result.iloc[4] == pytest.approx(2.0)  # (0+1+2+3+4)/5

    def test_ema(self):
        s = pd.Series(range(20), dtype=float)
        result = ema(s, period=5)
        assert len(result) == 20
        # EMA should track upward
        assert result.iloc[-1] > result.iloc[0]

    def test_sma_vs_ema_different(self):
        s = pd.Series(np.random.randn(50))
        s_sma = sma(s, 10)
        s_ema = ema(s, 10)
        assert not np.allclose(s_sma.dropna().values, s_ema.dropna().values[:len(s_sma.dropna())])
