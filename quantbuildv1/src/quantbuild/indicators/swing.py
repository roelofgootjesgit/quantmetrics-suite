"""Swing high/low and pivot detection."""
import numpy as np
import pandas as pd


def swing_highs(data: pd.DataFrame, lookback: int = 20, shift: bool = True) -> pd.Series:
    """Rolling highest high over lookback period.

    Args:
        shift: If True, uses previous bar's value (avoids look-ahead).
    """
    result = data["high"].rolling(lookback, center=False, min_periods=1).max()
    if shift:
        result = result.shift(1)
    return result


def swing_lows(data: pd.DataFrame, lookback: int = 20, shift: bool = True) -> pd.Series:
    """Rolling lowest low over lookback period.

    Args:
        shift: If True, uses previous bar's value (avoids look-ahead).
    """
    result = data["low"].rolling(lookback, center=False, min_periods=1).min()
    if shift:
        result = result.shift(1)
    return result


def pivot_highs(data: pd.DataFrame, pivot_bars: int = 2) -> pd.Series:
    """Identify pivot highs: bar whose high equals the max in a centered window.

    Returns boolean Series.
    """
    window = 2 * pivot_bars + 1
    high_roll = data["high"].rolling(window, center=True, min_periods=pivot_bars + 1).max()
    return (data["high"] == high_roll) & high_roll.notna()


def pivot_lows(data: pd.DataFrame, pivot_bars: int = 2) -> pd.Series:
    """Identify pivot lows: bar whose low equals the min in a centered window.

    Returns boolean Series.
    """
    window = 2 * pivot_bars + 1
    low_roll = data["low"].rolling(window, center=True, min_periods=pivot_bars + 1).min()
    return (data["low"] == low_roll) & low_roll.notna()


def last_swing_low(
    high: np.ndarray, low: np.ndarray, close: np.ndarray,
    end_idx: int, pivot_n: int = 3, lookback: int = 50,
) -> float:
    """Find the most recent swing low price before end_idx.

    Used for structure-based trailing stops on long trades.
    """
    start = max(0, end_idx - lookback)
    best = float("nan")
    for i in range(start + pivot_n, end_idx - pivot_n + 1):
        is_pivot = True
        for j in range(i - pivot_n, i + pivot_n + 1):
            if j == i or j < 0 or j >= len(low):
                continue
            if low[j] < low[i]:
                is_pivot = False
                break
        if is_pivot:
            best = float(low[i])
    return best


def last_swing_high(
    high: np.ndarray, low: np.ndarray, close: np.ndarray,
    end_idx: int, pivot_n: int = 3, lookback: int = 50,
) -> float:
    """Find the most recent swing high price before end_idx.

    Used for structure-based trailing stops on short trades.
    """
    start = max(0, end_idx - lookback)
    best = float("nan")
    for i in range(start + pivot_n, end_idx - pivot_n + 1):
        is_pivot = True
        for j in range(i - pivot_n, i + pivot_n + 1):
            if j == i or j < 0 or j >= len(high):
                continue
            if high[j] > high[i]:
                is_pivot = False
                break
        if is_pivot:
            best = float(high[i])
    return best
