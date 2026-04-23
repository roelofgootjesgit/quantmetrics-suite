"""Displacement – ICT strong directional move."""
import pandas as pd
import numpy as np
from typing import Dict

from src.quantbuild.strategy_modules.base import BaseModule


class DisplacementModule(BaseModule):
    @property
    def name(self) -> str:
        return "Displacement"

    @property
    def description(self) -> str:
        return "ICT institutional momentum – strong directional moves"

    def get_config_schema(self) -> Dict:
        return {
            "fields": [
                {"name": "min_body_pct", "label": "Min Body %", "type": "number", "default": 70, "min": 50, "max": 90},
                {"name": "min_candles", "label": "Min Consecutive Candles", "type": "number", "default": 3, "min": 2, "max": 10},
                {"name": "min_move_pct", "label": "Min Move %", "type": "number", "default": 1.5, "min": 0.5, "max": 5.0},
            ]
        }

    def calculate(self, data: pd.DataFrame, config: Dict) -> pd.DataFrame:
        df = data.copy()
        body_pct = config.get("min_body_pct", 70) / 100.0
        n_c = config.get("min_candles", 3)
        body = (df["close"] - df["open"]).abs()
        rng = df["high"] - df["low"]
        rng = rng.replace(0, np.nan)
        strong_bull = (df["close"] > df["open"]) & (body >= rng * body_pct)
        strong_bear = (df["close"] < df["open"]) & (body >= rng * body_pct)
        df["bullish_disp"] = strong_bull.rolling(n_c).sum() >= n_c
        df["bearish_disp"] = strong_bear.rolling(n_c).sum() >= n_c
        return df

    def check_entry_condition(self, data: pd.DataFrame, index: int, config: Dict, direction: str) -> bool:
        if index >= len(data):
            return False
        row = data.iloc[index]
        if direction == "LONG":
            return bool(row.get("bullish_disp", False))
        if direction == "SHORT":
            return bool(row.get("bearish_disp", False))
        return False
