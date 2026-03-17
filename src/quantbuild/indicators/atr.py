"""Average True Range and related volatility indicators."""
import numpy as np
import pandas as pd


def true_range(data: pd.DataFrame) -> pd.Series:
    """True Range: max(high-low, |high-prev_close|, |low-prev_close|).

    Falls back to high-low when previous close is unavailable.
    """
    hl = data["high"] - data["low"]
    if "close" not in data.columns or len(data) < 2:
        return hl
    prev_close = data["close"].shift(1)
    hc = (data["high"] - prev_close).abs()
    lc = (data["low"] - prev_close).abs()
    tr = pd.concat([hl, hc, lc], axis=1).max(axis=1)
    return tr.fillna(hl)


def atr(data: pd.DataFrame, period: int = 14, min_periods: int = 1) -> pd.Series:
    """Average True Range over rolling window."""
    tr = true_range(data)
    return tr.rolling(period, min_periods=min_periods).mean()


def atr_ratio(
    data: pd.DataFrame,
    atr_period: int = 14,
    sma_period: int = 20,
) -> pd.Series:
    """ATR / SMA(ATR) — volatility expansion/compression gauge.

    > 1.5 typically = expansion, < 0.7 = compression.
    """
    _atr = atr(data, period=atr_period)
    _atr_sma = _atr.rolling(sma_period, min_periods=1).mean()
    ratio = (_atr / _atr_sma).replace([np.inf, -np.inf], 1.0).fillna(1.0)
    return ratio
