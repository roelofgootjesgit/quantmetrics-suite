"""Market Structure Shift (MSS) – ICT structure break."""
import pandas as pd
import numpy as np
from typing import Dict

from src.quantbuild.strategy_modules.base import BaseModule


class MarketStructureShiftModule(BaseModule):
    @property
    def name(self) -> str:
        return "Market Structure Shift (MSS)"

    @property
    def description(self) -> str:
        return "ICT trend reversals – structure break detection"

    def get_config_schema(self) -> Dict:
        return {
            "fields": [
                {"name": "swing_lookback", "label": "Swing Lookback", "type": "number", "default": 5, "min": 3, "max": 20},
                {"name": "break_threshold_pct", "label": "Break Threshold %", "type": "number", "default": 0.2, "min": 0.1, "max": 1.0},
            ]
        }

    def calculate(self, data: pd.DataFrame, config: Dict) -> pd.DataFrame:
        df = data.copy()
        lb = config.get("swing_lookback", 5)
        thresh = config.get("break_threshold_pct", 0.2) / 100.0
        df["swing_high"] = df["high"].rolling(2 * lb + 1, center=True).max()
        df["swing_low"] = df["low"].rolling(2 * lb + 1, center=True).min()
        df["bullish_mss"] = (df["high"] >= df["swing_high"].shift(1) * (1 + thresh)) & (df["swing_high"].shift(1).notna())
        df["bearish_mss"] = (df["low"] <= df["swing_low"].shift(1) * (1 - thresh)) & (df["swing_low"].shift(1).notna())
        return df

    def check_entry_condition(self, data: pd.DataFrame, index: int, config: Dict, direction: str) -> bool:
        if index >= len(data):
            return False
        row = data.iloc[index]
        if direction == "LONG":
            return bool(row.get("bullish_mss", False))
        if direction == "SHORT":
            return bool(row.get("bearish_mss", False))
        return False
