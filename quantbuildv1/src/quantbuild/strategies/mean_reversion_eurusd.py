"""
Mean Reversion Strategy for EURUSD — COMPRESSION regime only.

Based on diagnostic findings:
  - EURUSD COMPRESSION: +0.286R/trade, 43% WR, PF 1.50
  - 73% of losers were initially profitable (MFE > 1R)
  - Entries work, but trend exits fail -> need fast fixed exits

Entry logic:
  1. Must be in COMPRESSION regime
  2. Liquidity sweep at range boundary (fake breakout)
  3. Wick rejection (reversal candle pattern)
  4. Optional: RSI extreme (>70 short, <30 long)

Exit logic (the critical fix):
  - Fixed TP: 0.8R - 1.2R (NO trailing, NO runners)
  - Time stop: 8-12 bars (if not hit TP/SL, exit at market)
  - Tight SL: 1.0R

This is the opposite of the trend system:
  - Trend: let winners run
  - Mean reversion: take profit fast, time is your enemy
"""
from typing import Dict, Any, Optional, Tuple

import numpy as np
import pandas as pd

from src.quantbuild.indicators.atr import atr as compute_atr


DEFAULT_MR_CONFIG = {
    "regime_filter": "compression",
    "range_lookback": 30,
    "sweep_threshold_pct": 0.05,
    "wick_ratio_min": 0.45,
    "rsi_period": 14,
    "rsi_overbought": 70,
    "rsi_oversold": 30,
    "use_rsi_filter": False,
    "require_sweep": True,
    "require_wick": False,
    "min_bars_between_trades": 8,
    "tp_r": 1.0,
    "sl_r": 1.0,
    "time_stop_bars": 10,
}


def compute_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """Relative Strength Index."""
    delta = close.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.rolling(period, min_periods=1).mean()
    avg_loss = loss.rolling(period, min_periods=1).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return rsi.fillna(50)


def compute_range_boundaries(data: pd.DataFrame, lookback: int = 30) -> Tuple[pd.Series, pd.Series]:
    """Rolling range high and low for compression detection."""
    range_high = data["high"].rolling(lookback, min_periods=lookback).max().shift(1)
    range_low = data["low"].rolling(lookback, min_periods=lookback).min().shift(1)
    return range_high, range_low


def detect_wick_rejection(data: pd.DataFrame, min_wick_ratio: float = 0.6) -> Tuple[pd.Series, pd.Series]:
    """Detect candles with long wicks (rejection of extreme price).

    Bullish rejection: long lower wick (buyers stepped in)
    Bearish rejection: long upper wick (sellers stepped in)
    """
    body = (data["close"] - data["open"]).abs()
    total_range = (data["high"] - data["low"]).replace(0, np.nan)

    lower_wick = pd.concat([data["open"], data["close"]], axis=1).min(axis=1) - data["low"]
    upper_wick = data["high"] - pd.concat([data["open"], data["close"]], axis=1).max(axis=1)

    lower_wick_ratio = lower_wick / total_range
    upper_wick_ratio = upper_wick / total_range

    bullish_rejection = lower_wick_ratio >= min_wick_ratio
    bearish_rejection = upper_wick_ratio >= min_wick_ratio

    return bullish_rejection.fillna(False), bearish_rejection.fillna(False)


def detect_range_sweep(
    data: pd.DataFrame,
    range_high: pd.Series,
    range_low: pd.Series,
    threshold_pct: float = 0.15,
) -> Tuple[pd.Series, pd.Series]:
    """Detect when price sweeps beyond range boundary then reverses.

    Bullish sweep: price dips below range_low then closes back inside
    Bearish sweep: price pokes above range_high then closes back inside
    """
    thresh_low = range_low * (1 - threshold_pct / 100)
    thresh_high = range_high * (1 + threshold_pct / 100)

    swept_low = data["low"] <= thresh_low
    closed_back_above = data["close"] > range_low
    bullish_sweep = swept_low & closed_back_above

    swept_high = data["high"] >= thresh_high
    closed_back_below = data["close"] < range_high
    bearish_sweep = swept_high & closed_back_below

    return bullish_sweep.fillna(False), bearish_sweep.fillna(False)


def run_mr_conditions(
    data: pd.DataFrame,
    direction: str,
    config: Optional[Dict[str, Any]] = None,
    regime_series: Optional[pd.Series] = None,
) -> pd.Series:
    """Generate mean reversion entry signals for EURUSD.

    Returns boolean Series where True = valid entry bar.
    """
    cfg = {**DEFAULT_MR_CONFIG, **(config or {})}
    n = len(data)

    lookback = cfg["range_lookback"]
    range_high, range_low = compute_range_boundaries(data, lookback)

    bullish_sweep, bearish_sweep = detect_range_sweep(
        data, range_high, range_low, cfg["sweep_threshold_pct"]
    )

    bullish_wick, bearish_wick = detect_wick_rejection(data, cfg["wick_ratio_min"])

    entries = pd.Series(False, index=data.index)

    need_sweep = cfg.get("require_sweep", True)
    need_wick = cfg.get("require_wick", False)

    if direction == "LONG":
        if need_sweep and need_wick:
            entries = bullish_sweep & bullish_wick
        elif need_sweep:
            entries = bullish_sweep
        elif need_wick:
            entries = bullish_wick
    elif direction == "SHORT":
        if need_sweep and need_wick:
            entries = bearish_sweep & bearish_wick
        elif need_sweep:
            entries = bearish_sweep
        elif need_wick:
            entries = bearish_wick

    # RSI filter (optional)
    if cfg.get("use_rsi_filter", False):
        rsi = compute_rsi(data["close"], cfg["rsi_period"])
        if direction == "LONG":
            entries = entries & (rsi < cfg["rsi_oversold"])
        elif direction == "SHORT":
            entries = entries & (rsi > cfg["rsi_overbought"])

    # Regime filter: only COMPRESSION
    if regime_series is not None:
        regime_filter = cfg.get("regime_filter", "compression")
        entries = entries & (regime_series == regime_filter)

    # Need enough data for range calculation
    entries.iloc[:lookback + 1] = False

    # Cooldown: minimum bars between trades
    min_gap = cfg.get("min_bars_between_trades", 0)
    if min_gap > 0:
        entry_indices = entries[entries].index.tolist()
        filtered = set()
        last_entry_pos = -min_gap - 1
        for idx in entry_indices:
            pos = data.index.get_loc(idx)
            if pos - last_entry_pos >= min_gap:
                filtered.add(idx)
                last_entry_pos = pos
        entries = pd.Series(False, index=data.index)
        entries[list(filtered)] = True

    return entries


def simulate_mr_trade(
    cache: dict,
    i: int,
    direction: str,
    tp_r: float = 1.0,
    sl_r: float = 1.0,
    time_stop_bars: int = 10,
) -> Dict[str, float]:
    """Simulate a mean reversion trade with fixed TP, tight SL, and time stop.

    Returns dict with pnl_r, mfe, mae, bars_held, exit_type.
    """
    close_arr = cache["close"]
    high_arr = cache["high"]
    low_arr = cache["low"]
    atr_arr = cache["atr"]
    n = len(close_arr)

    entry = float(close_arr[i])
    atr_val = float(atr_arr[i])
    risk = atr_val if atr_val > 0 else entry * 0.005

    if direction == "LONG":
        tp_price = entry + tp_r * risk
        sl_price = entry - sl_r * risk
    else:
        tp_price = entry - tp_r * risk
        sl_price = entry + sl_r * risk

    mfe = 0.0
    mae = 0.0

    for j in range(i + 1, min(i + time_stop_bars + 1, n)):
        bars_held = j - i
        h = float(high_arr[j])
        l = float(low_arr[j])

        if direction == "LONG":
            fav = (h - entry) / risk
            adv = (entry - l) / risk
        else:
            fav = (entry - l) / risk
            adv = (h - entry) / risk

        mfe = max(mfe, fav)
        mae = max(mae, adv)

        # Check SL first (conservative)
        if direction == "LONG" and l <= sl_price:
            return {"pnl_r": -sl_r, "mfe": mfe, "mae": mae, "bars_held": bars_held, "exit_type": "sl"}
        if direction == "SHORT" and h >= sl_price:
            return {"pnl_r": -sl_r, "mfe": mfe, "mae": mae, "bars_held": bars_held, "exit_type": "sl"}

        # Check TP
        if direction == "LONG" and h >= tp_price:
            return {"pnl_r": tp_r, "mfe": mfe, "mae": mae, "bars_held": bars_held, "exit_type": "tp"}
        if direction == "SHORT" and l <= tp_price:
            return {"pnl_r": tp_r, "mfe": mfe, "mae": mae, "bars_held": bars_held, "exit_type": "tp"}

    # Time stop: exit at close of last bar
    last_idx = min(i + time_stop_bars, n - 1)
    last_close = float(close_arr[last_idx])
    if direction == "LONG":
        pnl = (last_close - entry) / risk
    else:
        pnl = (entry - last_close) / risk

    return {"pnl_r": float(pnl), "mfe": mfe, "mae": mae, "bars_held": last_idx - i, "exit_type": "time"}
