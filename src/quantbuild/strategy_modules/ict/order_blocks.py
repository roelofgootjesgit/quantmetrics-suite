"""Order Blocks – ICT last candle before reversal."""
import pandas as pd
import numpy as np
from typing import Dict

from src.quantbuild.strategy_modules.base import BaseModule


class OrderBlockModule(BaseModule):
    @property
    def name(self) -> str:
        return "Order Blocks (OB)"

    @property
    def description(self) -> str:
        return "ICT institutional order zones – last candle before reversal"

    def get_config_schema(self) -> Dict:
        return {
            "fields": [
                {"name": "min_candles", "label": "Min Reversal Candles", "type": "number", "default": 3, "min": 2, "max": 10},
                {"name": "min_move_pct", "label": "Min Move %", "type": "number", "default": 3.0, "min": 1.0, "max": 10.0},
                {"name": "validity_candles", "label": "OB Validity", "type": "number", "default": 20, "min": 10, "max": 100},
            ]
        }

    def calculate(self, data: pd.DataFrame, config: Dict) -> pd.DataFrame:
        df = data.copy()
        n_c = config.get("min_candles", 3)
        move_pct = config.get("min_move_pct", 3.0) / 100.0
        validity = config.get("validity_candles", 20)

        high = df["high"].values
        low = df["low"].values
        close = df["close"].values
        openp = df["open"].values
        n = len(df)

        bullish_ob = np.zeros(n, dtype=bool)
        bearish_ob = np.zeros(n, dtype=bool)

        for i in range(n_c + 1, n - n_c):
            fwd_high = high[i + 1: i + 1 + n_c].max()
            fwd_low = low[i + 1: i + 1 + n_c].min()

            if close[i] < openp[i] and fwd_high > high[i]:
                move = (fwd_high - low[i]) / low[i] if low[i] > 0 else 0
                if move >= move_pct:
                    bearish_ob[i] = True

            if close[i] > openp[i] and fwd_low < low[i]:
                move = (high[i] - fwd_low) / high[i] if high[i] > 0 else 0
                if move >= move_pct:
                    bullish_ob[i] = True

        df["bullish_ob"] = bullish_ob
        df["bearish_ob"] = bearish_ob
        df["in_bullish_ob"] = pd.Series(bullish_ob, index=df.index).rolling(window=validity, min_periods=1).max().fillna(0).astype(bool)
        df["in_bearish_ob"] = pd.Series(bearish_ob, index=df.index).rolling(window=validity, min_periods=1).max().fillna(0).astype(bool)
        return df

    def check_entry_condition(self, data: pd.DataFrame, index: int, config: Dict, direction: str) -> bool:
        if index >= len(data):
            return False
        row = data.iloc[index]
        if direction == "LONG":
            return bool(row.get("in_bullish_ob", False))
        if direction == "SHORT":
            return bool(row.get("in_bearish_ob", False))
        return False
