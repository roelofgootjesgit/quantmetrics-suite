"""Imbalance Zones – ICT wick-based gaps."""
import pandas as pd
import numpy as np
from typing import Dict

from src.quantbuild.strategy_modules.base import BaseModule


class ImbalanceZonesModule(BaseModule):
    @property
    def name(self) -> str:
        return "Imbalance Zones"

    @property
    def description(self) -> str:
        return "ICT wick-based gaps – price imbalances to fill"

    def get_config_schema(self) -> Dict:
        return {
            "fields": [
                {"name": "min_gap_size", "label": "Min Gap Size", "type": "number", "default": 0.5, "min": 0.1, "max": 10.0},
                {"name": "validity_candles", "label": "Validity Candles", "type": "number", "default": 50, "min": 20, "max": 200},
            ]
        }

    def calculate(self, data: pd.DataFrame, config: Dict) -> pd.DataFrame:
        df = data.copy()
        min_gap = config.get("min_gap_size", 0.5)
        validity = config.get("validity_candles", 50)

        high = df["high"].values
        low = df["low"].values
        n = len(df)

        bullish_imb = np.zeros(n, dtype=bool)
        bearish_imb = np.zeros(n, dtype=bool)

        if n >= 3:
            bull_gap = low[2:] - high[:-2]
            bullish_imb[1:-1] = bull_gap > min_gap

            bear_gap = low[:-2] - high[2:]
            bearish_imb[1:-1] = bear_gap > min_gap

        df["bullish_imbalance"] = bullish_imb
        df["bearish_imbalance"] = bearish_imb
        df["in_bullish_imbalance"] = pd.Series(bullish_imb, index=df.index).rolling(window=validity, min_periods=1).max().fillna(0).astype(bool)
        df["in_bearish_imbalance"] = pd.Series(bearish_imb, index=df.index).rolling(window=validity, min_periods=1).max().fillna(0).astype(bool)
        return df

    def check_entry_condition(self, data: pd.DataFrame, index: int, config: Dict, direction: str) -> bool:
        if index >= len(data):
            return False
        row = data.iloc[index]
        if direction == "LONG":
            return bool(row.get("in_bullish_imbalance", False))
        if direction == "SHORT":
            return bool(row.get("in_bearish_imbalance", False))
        return False
