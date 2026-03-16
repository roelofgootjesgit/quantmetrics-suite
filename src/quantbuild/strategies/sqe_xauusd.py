"""
SQE (Smart Quality Entry) for XAUUSD – 3-pillar model.

  1. Trend context    – structure/momentum
  2. Liquidity/levels – sweep + FVG
  3. Entry timing     – displacement trigger
"""
from typing import Dict, Any, List
import pandas as pd

from src.quantbuild.strategy_modules.ict.liquidity_sweep import LiquiditySweepModule
from src.quantbuild.strategy_modules.ict.displacement import DisplacementModule
from src.quantbuild.strategy_modules.ict.fair_value_gaps import FairValueGapModule
from src.quantbuild.strategy_modules.ict.market_structure_shift import MarketStructureShiftModule
from src.quantbuild.strategy_modules.ict.structure_context import add_structure_context
from src.quantbuild.strategy_modules.ict.order_blocks import OrderBlockModule
from src.quantbuild.strategy_modules.ict.imbalance_zones import ImbalanceZonesModule


DEFAULT_MODULE_CONFIG = {
    "liquidity_sweep": {"lookback_candles": 20, "sweep_threshold_pct": 0.2, "reversal_candles": 3},
    "displacement": {"min_body_pct": 70, "min_candles": 3, "min_move_pct": 1.5},
    "fair_value_gaps": {"min_gap_pct": 0.5, "validity_candles": 50},
    "market_structure_shift": {"swing_lookback": 5, "break_threshold_pct": 0.2},
    "structure_context": {"lookback": 30, "pivot_bars": 2},
    "order_blocks": {"min_candles": 2, "min_move_pct": 1.5, "validity_candles": 40},
    "imbalance_zones": {"min_gap_size": 3.0, "validity_candles": 50},
}


def get_sqe_default_config() -> Dict[str, Any]:
    return {
        **DEFAULT_MODULE_CONFIG,
        "trend_context": {
            "modules": ["market_structure_shift", "displacement"],
            "require_all": False,
        },
        "liquidity_levels": {
            "modules": ["liquidity_sweep", "fair_value_gaps"],
            "require_all": True,
        },
        "entry_trigger": {
            "module": "displacement",
        },
        "require_structure": True,
        "entry_require_sweep_displacement_fvg": True,
        "entry_sweep_disp_fvg_lookback_bars": 5,
    }


def _get_signal_series(df: pd.DataFrame, module: str, direction: str) -> pd.Series:
    if direction == "LONG":
        key = {
            "liquidity_sweep": "bullish_sweep",
            "displacement": "bullish_disp",
            "fair_value_gaps": "in_bullish_fvg",
            "market_structure_shift": "bullish_mss",
            "order_blocks": "in_bullish_ob",
            "imbalance_zones": "in_bullish_imbalance",
        }.get(module)
    else:
        key = {
            "liquidity_sweep": "bearish_sweep",
            "displacement": "bearish_disp",
            "fair_value_gaps": "in_bearish_fvg",
            "market_structure_shift": "bearish_mss",
            "order_blocks": "in_bearish_ob",
            "imbalance_zones": "in_bearish_imbalance",
        }.get(module)
    if key and key in df.columns:
        return df[key].fillna(False)
    return pd.Series(False, index=df.index)


def _combine_pillar(df: pd.DataFrame, modules: List[str], require_all: bool, direction: str) -> pd.Series:
    if not modules:
        return pd.Series(True, index=df.index)
    series = [_get_signal_series(df, m, direction) for m in modules]
    if require_all:
        out = series[0]
        for s in series[1:]:
            out = out & s
        return out
    out = series[0]
    for s in series[1:]:
        out = out | s
    return out


def _compute_modules_once(data: pd.DataFrame, config: Dict[str, Any]) -> pd.DataFrame:
    """Run all ICT modules once. Results contain both bullish and bearish columns."""
    cfg = config or get_sqe_default_config()
    df = data.copy()

    df = LiquiditySweepModule().calculate(df, cfg.get("liquidity_sweep", {}))
    df = DisplacementModule().calculate(df, cfg.get("displacement", {}))
    df = FairValueGapModule().calculate(df, cfg.get("fair_value_gaps", {}))
    df = MarketStructureShiftModule().calculate(df, cfg.get("market_structure_shift", {}))
    df = OrderBlockModule().calculate(df, cfg.get("order_blocks", {"min_candles": 2, "min_move_pct": 1.5, "validity_candles": 40}))
    df = ImbalanceZonesModule().calculate(df, cfg.get("imbalance_zones", {"min_gap_size": 3.0, "validity_candles": 50}))
    df = add_structure_context(df, cfg.get("structure_context", {"lookback": 30, "pivot_bars": 2}), inplace=True)
    return df


def _apply_direction_filter(df: pd.DataFrame, direction: str, config: Dict[str, Any]) -> pd.Series:
    cfg = config or get_sqe_default_config()

    if cfg.get("require_structure", True):
        structure_ok = df["in_bullish_structure"] if direction == "LONG" else df["in_bearish_structure"]
    else:
        structure_ok = pd.Series(True, index=df.index)

    tc_cfg = cfg.get("trend_context") or get_sqe_default_config()["trend_context"]
    trend_ok = _combine_pillar(df, tc_cfg.get("modules", []), tc_cfg.get("require_all", False), direction)

    liq_cfg = cfg.get("liquidity_levels") or get_sqe_default_config()["liquidity_levels"]
    liquidity_ok = _combine_pillar(df, liq_cfg.get("modules", []), liq_cfg.get("require_all", True), direction)

    trig_cfg = cfg.get("entry_trigger") or get_sqe_default_config()["entry_trigger"]
    trigger_ok = _get_signal_series(df, trig_cfg.get("module", "displacement"), direction)

    if cfg.get("entry_require_sweep_displacement_fvg", False):
        core_modules = ["liquidity_sweep", "displacement", "fair_value_gaps"]
        entry_modules = cfg.get("entry_combo_modules", core_modules)
        raw_signals = [_get_signal_series(df, m, direction) for m in entry_modules]
        lookback = max(0, int(cfg.get("entry_sweep_disp_fvg_lookback_bars", 0)))
        min_count = max(1, int(cfg.get("entry_sweep_disp_fvg_min_count", 3)))

        if lookback > 0:
            signals = [s.rolling(window=lookback, min_periods=1).max().fillna(0).astype(bool) for s in raw_signals]
        else:
            signals = raw_signals

        count_series = signals[0].astype(int)
        for s in signals[1:]:
            count_series = count_series + s.astype(int)

        combined = structure_ok & (count_series >= min_count)
    else:
        combined = trend_ok & liquidity_ok & trigger_ok & structure_ok

    return combined.fillna(False)


def run_sqe_conditions(
    data: pd.DataFrame,
    direction: str,
    config: Dict[str, Any] | None = None,
    _precomputed_df: pd.DataFrame | None = None,
) -> pd.Series:
    """Run the 3-pillar model. Returns boolean series where entry is valid."""
    cfg = config or get_sqe_default_config()
    if _precomputed_df is not None:
        df = _precomputed_df
    else:
        df = _compute_modules_once(data, cfg)
    return _apply_direction_filter(df, direction, cfg)
