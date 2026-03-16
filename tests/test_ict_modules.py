"""Unit tests for ICT strategy modules."""
import numpy as np
import pandas as pd
import pytest

from src.quantbuild.strategy_modules.ict.liquidity_sweep import LiquiditySweepModule
from src.quantbuild.strategy_modules.ict.displacement import DisplacementModule
from src.quantbuild.strategy_modules.ict.fair_value_gaps import FairValueGapModule
from src.quantbuild.strategy_modules.ict.market_structure_shift import MarketStructureShiftModule
from src.quantbuild.strategy_modules.ict.order_blocks import OrderBlockModule
from src.quantbuild.strategy_modules.ict.imbalance_zones import ImbalanceZonesModule
from src.quantbuild.strategy_modules.ict.structure_context import compute_structure_labels, add_structure_context


def _make_ohlcv(n: int = 100, base: float = 2000.0, seed: int = 42) -> pd.DataFrame:
    rng = np.random.RandomState(seed)
    dates = pd.date_range("2025-01-01", periods=n, freq="15min", tz="UTC")
    close = base + np.cumsum(rng.randn(n) * 2)
    high = close + rng.uniform(0.5, 3.0, n)
    low = close - rng.uniform(0.5, 3.0, n)
    opn = close + rng.randn(n) * 0.5
    return pd.DataFrame({"open": opn, "high": high, "low": low, "close": close, "volume": rng.randint(100, 1000, n)}, index=dates)


class TestLiquiditySweep:
    def test_output_columns(self):
        result = LiquiditySweepModule().calculate(_make_ohlcv(), {"lookback_candles": 20, "sweep_threshold_pct": 0.2, "reversal_candles": 3})
        for col in ["bullish_sweep", "bearish_sweep", "swept_low", "swept_high"]:
            assert col in result.columns

    def test_boolean_types(self):
        result = LiquiditySweepModule().calculate(_make_ohlcv(), {"lookback_candles": 20, "sweep_threshold_pct": 0.2, "reversal_candles": 3})
        assert result["bullish_sweep"].dtype == bool

    def test_check_entry(self):
        cfg = {"lookback_candles": 20, "sweep_threshold_pct": 0.2, "reversal_candles": 3}
        result = LiquiditySweepModule().calculate(_make_ohlcv(), cfg)
        assert isinstance(LiquiditySweepModule().check_entry_condition(result, 50, cfg, "LONG"), bool)


class TestDisplacement:
    def test_output_columns(self):
        result = DisplacementModule().calculate(_make_ohlcv(), {"min_body_pct": 70, "min_candles": 3, "min_move_pct": 1.5})
        assert "bullish_disp" in result.columns and "bearish_disp" in result.columns


class TestFairValueGaps:
    def test_output_columns(self):
        result = FairValueGapModule().calculate(_make_ohlcv(), {"min_gap_pct": 0.5, "validity_candles": 50})
        for col in ["bullish_fvg", "bearish_fvg", "in_bullish_fvg", "in_bearish_fvg"]:
            assert col in result.columns


class TestMarketStructureShift:
    def test_output_columns(self):
        result = MarketStructureShiftModule().calculate(_make_ohlcv(), {"swing_lookback": 5, "break_threshold_pct": 0.2})
        assert "bullish_mss" in result.columns and "bearish_mss" in result.columns


class TestOrderBlocks:
    def test_output_columns(self):
        result = OrderBlockModule().calculate(_make_ohlcv(200), {"min_candles": 3, "min_move_pct": 3.0, "validity_candles": 20})
        for col in ["bullish_ob", "bearish_ob", "in_bullish_ob", "in_bearish_ob"]:
            assert col in result.columns


class TestImbalanceZones:
    def test_output_columns(self):
        result = ImbalanceZonesModule().calculate(_make_ohlcv(), {"min_gap_size": 0.5, "validity_candles": 50})
        for col in ["bullish_imbalance", "bearish_imbalance"]:
            assert col in result.columns


class TestStructureContext:
    def test_labels_values(self):
        labels = compute_structure_labels(_make_ohlcv(200), lookback=30, pivot_bars=2)
        assert set(labels.unique()).issubset({"BULLISH_STRUCTURE", "BEARISH_STRUCTURE", "RANGE"})

    def test_add_structure_context(self):
        result = add_structure_context(_make_ohlcv(200), {"lookback": 30, "pivot_bars": 2})
        assert "structure_label" in result.columns
        assert "in_bullish_structure" in result.columns
