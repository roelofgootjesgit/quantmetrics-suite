"""
SQE (Smart Quality Entry) for XAUUSD – 3-pillar model.

  1. Trend context    – structure/momentum
  2. Liquidity/levels – sweep + FVG
  3. Entry timing     – displacement trigger
"""
from typing import Any, Dict, List
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


def _row_bool(row: pd.Series, col: str) -> bool:
    if col not in row.index:
        return False
    v = row[col]
    try:
        if pd.isna(v):
            return False
    except (TypeError, ValueError):
        pass
    return bool(v)


def _row_float(row: pd.Series, col: str, default: float = 0.0) -> float:
    if col not in row.index:
        return default
    v = row[col]
    try:
        if pd.isna(v):
            return default
    except (TypeError, ValueError):
        return default
    try:
        f = float(v)
    except (TypeError, ValueError):
        return default
    if pd.isna(f):
        return default
    return round(f, 4)


def sqe_decision_context_at_bar(
    df: pd.DataFrame,
    direction: str,
    bar_index: int,
    config: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """JSON-serializable SQE attribution snapshot at a single bar (for QuantLog / research).

    Mirrors ``_apply_direction_filter`` so logged flags match the actual entry boolean.
    """
    cfg = config or get_sqe_default_config()
    if bar_index < 0 or bar_index >= len(df):
        return {
            "decision_context_version": 1,
            "strategy": "sqe_xauusd",
            "direction": direction,
            "error": "bar_index_out_of_range",
        }

    row = df.iloc[bar_index]
    if direction == "LONG":
        structure_col = "in_bullish_structure"
        module_cols = {
            "mss_confirmed": "bullish_mss",
            "sweep_detected": "bullish_sweep",
            "fvg_in_zone": "in_bullish_fvg",
            "displacement_trigger": "bullish_disp",
        }
    else:
        structure_col = "in_bearish_structure"
        module_cols = {
            "mss_confirmed": "bearish_mss",
            "sweep_detected": "bearish_sweep",
            "fvg_in_zone": "in_bearish_fvg",
            "displacement_trigger": "bearish_disp",
        }

    flags = {k: _row_bool(row, col) for k, col in module_cols.items()}
    structure_column_true = _row_bool(row, structure_col)

    fvg_q_col = "bullish_fvg_quality" if direction == "LONG" else "bearish_fvg_quality"
    fvg_quality = _row_float(row, fvg_q_col, 0.0)

    tc_cfg = cfg.get("trend_context") or get_sqe_default_config()["trend_context"]
    trend_ok = bool(_combine_pillar(df, tc_cfg.get("modules", []), tc_cfg.get("require_all", False), direction).iloc[bar_index])

    liq_cfg = cfg.get("liquidity_levels") or get_sqe_default_config()["liquidity_levels"]
    liquidity_ok = bool(
        _combine_pillar(df, liq_cfg.get("modules", []), liq_cfg.get("require_all", True), direction).iloc[bar_index]
    )

    trig_cfg = cfg.get("entry_trigger") or get_sqe_default_config()["entry_trigger"]
    trigger_mod = trig_cfg.get("module", "displacement")
    trigger_ok = bool(_get_signal_series(df, trigger_mod, direction).iloc[bar_index])

    if cfg.get("require_structure", True):
        structure_ok = bool(structure_column_true)
    else:
        structure_ok = True

    entry_combo = bool(cfg.get("entry_require_sweep_displacement_fvg", False))
    combo_count: int | None = None
    combo_lookback: int | None = None
    combo_min_count: int | None = None
    entry_signal = False

    if entry_combo:
        core_modules = ["liquidity_sweep", "displacement", "fair_value_gaps"]
        entry_modules = cfg.get("entry_combo_modules", core_modules)
        raw_signals = [_get_signal_series(df, m, direction) for m in entry_modules]
        lookback = max(0, int(cfg.get("entry_sweep_disp_fvg_lookback_bars", 0)))
        min_count = max(1, int(cfg.get("entry_sweep_disp_fvg_min_count", 3)))
        combo_lookback = lookback
        combo_min_count = min_count

        if lookback > 0:
            signals = [s.rolling(window=lookback, min_periods=1).max().fillna(0).astype(bool) for s in raw_signals]
        else:
            signals = raw_signals

        count_series = signals[0].astype(int)
        for s in signals[1:]:
            count_series = count_series + s.astype(int)
        combo_count = int(count_series.iloc[bar_index])
        entry_signal = bool(structure_ok and (combo_count >= min_count))
    else:
        entry_signal = bool(trend_ok & liquidity_ok & trigger_ok & structure_ok)

    structure_label = row["structure_label"] if "structure_label" in row.index else None
    if structure_label is not None and not isinstance(structure_label, str):
        try:
            if pd.isna(structure_label):
                structure_label = None
            else:
                structure_label = str(structure_label)
        except (TypeError, ValueError):
            structure_label = str(structure_label)

    out: Dict[str, Any] = {
        "decision_context_version": 1,
        "strategy": "sqe_xauusd",
        "direction": direction,
        "entry_path": "sweep_disp_fvg_combo" if entry_combo else "classic_pillars",
        "structure_required": bool(cfg.get("require_structure", True)),
        "structure_column_true": structure_column_true,
        "trend_pillar_ok": trend_ok,
        "liquidity_pillar_ok": liquidity_ok,
        "trigger_ok": trigger_ok,
        "structure_ok": structure_ok,
        "entry_signal": entry_signal,
        "fvg_quality": fvg_quality,
        **flags,
    }
    if structure_label is not None:
        out["structure_label"] = structure_label
    if entry_combo:
        out["combo_lookback_bars"] = combo_lookback
        out["combo_min_modules"] = combo_min_count
        out["combo_active_modules_count"] = combo_count
    return out
