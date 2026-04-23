"""Fair Value Gaps (FVG) – ICT price imbalance."""
import pandas as pd
import numpy as np
from typing import Dict

from src.quantbuild.strategy_modules.base import BaseModule


class FairValueGapModule(BaseModule):
    @property
    def name(self) -> str:
        return "Fair Value Gaps (FVG)"

    @property
    def description(self) -> str:
        return "ICT price imbalances – gaps that tend to fill"

    def get_config_schema(self) -> Dict:
        return {
            "fields": [
                {"name": "min_gap_pct", "label": "Min Gap %", "type": "number", "default": 0.5, "min": 0.1, "max": 2.0},
                {"name": "validity_candles", "label": "Validity Candles", "type": "number", "default": 50, "min": 10, "max": 100},
                {
                    "name": "fvg_quality_cap_pct",
                    "label": "FVG quality cap % (gap ratio at this size → quality 1.0)",
                    "type": "number",
                    "default": 1.5,
                    "min": 0.2,
                    "max": 5.0,
                },
            ]
        }

    def calculate(self, data: pd.DataFrame, config: Dict) -> pd.DataFrame:
        df = data.copy()
        min_gap = config.get("min_gap_pct", 0.5) / 100.0
        validity = config.get("validity_candles", 50)
        cap_ratio = max(float(config.get("fvg_quality_cap_pct", 1.5)) / 100.0, 1e-9)

        high = df["high"].values
        low = df["low"].values
        n = len(df)

        prev_prev_high = np.empty(n)
        prev_prev_high[:2] = np.nan
        prev_prev_high[2:] = high[:-2]

        bull_gap = (low - prev_prev_high) / np.where(prev_prev_high != 0, prev_prev_high, np.nan)
        bull_mask = (low > prev_prev_high) & (bull_gap >= min_gap)
        bullish_fvg = np.zeros(n, dtype=bool)
        bullish_fvg[1:-1] = bull_mask[2:]

        prev_prev_low = np.empty(n)
        prev_prev_low[:2] = np.nan
        prev_prev_low[2:] = low[:-2]

        bear_gap = (prev_prev_low - high) / np.where(prev_prev_low != 0, prev_prev_low, np.nan)
        bear_mask = (high < prev_prev_low) & (bear_gap >= min_gap)
        bearish_fvg = np.zeros(n, dtype=bool)
        bearish_fvg[1:-1] = bear_mask[2:]

        # Quality 0–1: gap size vs cap (same validity window as in_*_fvg)
        bull_qual_form = np.zeros(n, dtype=np.float64)
        bear_qual_form = np.zeros(n, dtype=np.float64)
        for j in range(1, n - 1):
            if bullish_fvg[j]:
                g = bull_gap[j + 1]
                if np.isfinite(g) and g >= min_gap:
                    bull_qual_form[j] = min(1.0, float(g / cap_ratio))
            if bearish_fvg[j]:
                g = bear_gap[j + 1]
                if np.isfinite(g) and g >= min_gap:
                    bear_qual_form[j] = min(1.0, float(g / cap_ratio))

        df["bullish_fvg"] = bullish_fvg
        df["bearish_fvg"] = bearish_fvg
        df["in_bullish_fvg"] = df["bullish_fvg"].astype(int).rolling(window=validity, min_periods=1).max().astype(bool)
        df["in_bearish_fvg"] = df["bearish_fvg"].astype(int).rolling(window=validity, min_periods=1).max().astype(bool)
        df["bullish_fvg_quality"] = (
            pd.Series(bull_qual_form, index=df.index).rolling(window=validity, min_periods=1).max().fillna(0.0)
        )
        df["bearish_fvg_quality"] = (
            pd.Series(bear_qual_form, index=df.index).rolling(window=validity, min_periods=1).max().fillna(0.0)
        )
        return df

    def check_entry_condition(self, data: pd.DataFrame, index: int, config: Dict, direction: str) -> bool:
        if index >= len(data):
            return False
        row = data.iloc[index]
        if direction == "LONG":
            return bool(row.get("in_bullish_fvg", False))
        if direction == "SHORT":
            return bool(row.get("in_bearish_fvg", False))
        return False
