"""Liquidity Sweep – ICT stop hunt then reversal."""
import pandas as pd
import numpy as np
from typing import Dict

from src.quantbuild.strategy_modules.base import BaseModule


class LiquiditySweepModule(BaseModule):
    @property
    def name(self) -> str:
        return "Liquidity Sweep"

    @property
    def description(self) -> str:
        return "ICT stop hunts – fake breakouts before reversal"

    def get_config_schema(self) -> Dict:
        return {
            "fields": [
                {"name": "lookback_candles", "label": "Lookback", "type": "number", "default": 20, "min": 10, "max": 50},
                {"name": "sweep_threshold_pct", "label": "Sweep Threshold %", "type": "number", "default": 0.2, "min": 0.1, "max": 1.0},
                {"name": "reversal_candles", "label": "Reversal Window", "type": "number", "default": 3, "min": 1, "max": 5},
            ]
        }

    def calculate(self, data: pd.DataFrame, config: Dict) -> pd.DataFrame:
        df = data.copy()
        lookback = config.get("lookback_candles", 20)
        thresh = config.get("sweep_threshold_pct", 0.2) / 100.0
        rev_n = config.get("reversal_candles", 3)
        df["swing_high"] = df["high"].rolling(lookback, center=False).max().shift(1)
        df["swing_low"] = df["low"].rolling(lookback, center=False).min().shift(1)

        n = len(df)
        high_arr = df["high"].values.astype(np.float64)
        low_arr = df["low"].values.astype(np.float64)
        sh_arr = df["swing_high"].values.astype(np.float64)
        sl_arr = df["swing_low"].values.astype(np.float64)

        bullish_sweep = np.zeros(n, dtype=bool)
        bearish_sweep = np.zeros(n, dtype=bool)
        swept_low = np.full(n, np.nan)
        swept_high = np.full(n, np.nan)

        start = lookback + rev_n
        for i in range(start, n):
            sh = sh_arr[i - 1]
            sl_val = sl_arr[i - 1]
            if np.isnan(sh) or np.isnan(sl_val):
                continue

            h = high_arr[i]
            l_ = low_arr[i]

            if l_ <= sl_val * (1 - thresh):
                end_j = min(i + rev_n + 1, n)
                for j in range(i, end_j):
                    if high_arr[j] >= sl_val * (1 + thresh):
                        bullish_sweep[i] = True
                        swept_low[i] = sl_val
                        break

            if h >= sh * (1 + thresh):
                end_j = min(i + rev_n + 1, n)
                for j in range(i, end_j):
                    if low_arr[j] <= sh * (1 - thresh):
                        bearish_sweep[i] = True
                        swept_high[i] = sh
                        break

        df["bullish_sweep"] = bullish_sweep
        df["bearish_sweep"] = bearish_sweep
        df["swept_low"] = swept_low
        df["swept_high"] = swept_high
        return df

    def check_entry_condition(self, data: pd.DataFrame, index: int, config: Dict, direction: str) -> bool:
        if index >= len(data):
            return False
        row = data.iloc[index]
        if direction == "LONG":
            return bool(row.get("bullish_sweep", False))
        if direction == "SHORT":
            return bool(row.get("bearish_sweep", False))
        return False
