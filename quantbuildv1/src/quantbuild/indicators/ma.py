"""Moving average indicators."""
import pandas as pd


def sma(series: pd.Series, period: int, min_periods: int = 1) -> pd.Series:
    """Simple Moving Average."""
    return series.rolling(period, min_periods=min_periods).mean()


def ema(series: pd.Series, period: int) -> pd.Series:
    """Exponential Moving Average."""
    return series.ewm(span=period, adjust=False).mean()
