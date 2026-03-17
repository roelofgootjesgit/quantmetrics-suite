"""
Regime Detector — classifies market into TREND / EXPANSION / COMPRESSION.

Detection logic:
  - ATR ratio = current ATR / SMA(ATR, 20)
  - Structure from structure_context (BULLISH/BEARISH/RANGE)

  EXPANSION:   ATR ratio > expansion_threshold (default 1.5)
  COMPRESSION: ATR ratio < compression_threshold (default 0.7) OR structure = RANGE
  TREND:       everything else with clear directional structure
"""
import logging
from typing import Any, Dict, Optional

import numpy as np
import pandas as pd

from src.quantbuild.indicators.atr import atr_ratio as compute_atr_ratio
from src.quantbuild.strategy_modules.ict.structure_context import add_structure_context
from src.quantbuild.strategy_modules.ict.structure_labels import RANGE

logger = logging.getLogger(__name__)

REGIME_TREND = "trend"
REGIME_EXPANSION = "expansion"
REGIME_COMPRESSION = "compression"

ALL_REGIMES = (REGIME_TREND, REGIME_EXPANSION, REGIME_COMPRESSION)


class RegimeDetector:
    """Classify each bar into TREND / EXPANSION / COMPRESSION."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        cfg = config or {}
        self._atr_period = cfg.get("atr_period", 14)
        self._atr_sma_period = cfg.get("atr_sma_period", 20)
        self._expansion_threshold = cfg.get("expansion_threshold", 1.5)
        self._compression_threshold = cfg.get("compression_threshold", 0.7)
        self._structure_lookback = cfg.get("structure_lookback", 30)
        self._structure_pivot_bars = cfg.get("structure_pivot_bars", 2)

    def classify(
        self,
        data: pd.DataFrame,
        data_1h: Optional[pd.DataFrame] = None,
    ) -> pd.Series:
        """
        Classify each bar in data into a regime.

        Uses 1h data for structure if available (more reliable on higher TF),
        otherwise falls back to the input timeframe.
        """
        df = data.copy()

        ratio = compute_atr_ratio(df, atr_period=self._atr_period, sma_period=self._atr_sma_period)

        struct_cfg = {
            "lookback": self._structure_lookback,
            "pivot_bars": self._structure_pivot_bars,
        }

        if data_1h is not None and len(data_1h) >= 30:
            data_1h_s = add_structure_context(data_1h.copy(), struct_cfg)
            structure = data_1h_s["structure_label"].reindex(df.index, method="ffill")
        else:
            if "structure_label" not in df.columns:
                df = add_structure_context(df, struct_cfg)
            structure = df["structure_label"]

        structure = structure.fillna(RANGE)

        regimes = pd.Series(REGIME_TREND, index=df.index, dtype=object)
        regimes[ratio > self._expansion_threshold] = REGIME_EXPANSION
        is_compression = (ratio < self._compression_threshold) | (structure == RANGE)
        regimes[is_compression & (ratio <= self._expansion_threshold)] = REGIME_COMPRESSION

        counts = regimes.value_counts()
        total = len(regimes)
        logger.info(
            "Regime distribution: %s",
            " | ".join(f"{r}: {counts.get(r, 0)} ({100*counts.get(r, 0)/total:.1f}%%)" for r in ALL_REGIMES),
        )

        return regimes

    def classify_single(self, atr_ratio: float, structure_label: str) -> str:
        """Classify a single bar (for live usage)."""
        if atr_ratio > self._expansion_threshold:
            return REGIME_EXPANSION
        if atr_ratio < self._compression_threshold or structure_label == RANGE:
            return REGIME_COMPRESSION
        return REGIME_TREND
