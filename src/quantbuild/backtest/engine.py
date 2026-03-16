"""Backtest engine: load data, run strategy, record trades."""
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from src.quantbuild.models.trade import Trade, calculate_rr
from src.quantbuild.data.sessions import session_from_timestamp, ENTRY_SESSIONS
from src.quantbuild.io.parquet_loader import load_parquet, ensure_data
from src.quantbuild.strategies.sqe_xauusd import run_sqe_conditions, get_sqe_default_config, _compute_modules_once
from src.quantbuild.strategy_modules.ict.structure_context import add_structure_context

logger = logging.getLogger(__name__)


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> None:
    for k, v in override.items():
        if k in base and isinstance(base[k], dict) and isinstance(v, dict):
            _deep_merge(base[k], v)
        else:
            base[k] = v


def _apply_h1_gate(
    entries: pd.Series, data: pd.DataFrame, direction: str,
    base_path: Path, symbol: str, start: datetime, end: datetime,
    sqe_cfg: Dict[str, Any],
) -> pd.Series:
    data_1h = load_parquet(base_path, symbol, "1h", start=start, end=end)
    if data_1h.empty or len(data_1h) < 30:
        logger.info("H1-gate on but no 1h data; M15-only for %s", direction)
        return entries
    data_1h = data_1h.sort_index()
    struct_cfg = sqe_cfg.get("structure_context", {"lookback": 30, "pivot_bars": 2})
    data_1h = add_structure_context(data_1h, struct_cfg)
    if direction == "LONG":
        h1_filter = data_1h["in_bullish_structure"].reindex(data.index, method="ffill")
    else:
        h1_filter = data_1h["in_bearish_structure"].reindex(data.index, method="ffill")
    h1_filter = h1_filter.infer_objects(copy=False).fillna(False)
    filtered = entries & h1_filter
    logger.info("Entry bars %s (after H1-gate): %d", direction, int(filtered.sum()))
    return filtered


def _prepare_sim_cache(data: pd.DataFrame) -> dict:
    return {
        "close": data["close"].values.astype(np.float64),
        "high": data["high"].values.astype(np.float64),
        "low": data["low"].values.astype(np.float64),
        "atr": (data["high"] - data["low"]).rolling(14, min_periods=1).mean().values.astype(np.float64),
        "ts": data.index,
    }


def _simulate_trade(data: pd.DataFrame, i: int, direction: str, tp_r: float, sl_r: float, _cache: dict | None = None) -> dict:
    if _cache is not None:
        close_arr, high_arr, low_arr, atr_arr, ts_arr = _cache["close"], _cache["high"], _cache["low"], _cache["atr"], _cache["ts"]
    else:
        close_arr = data["close"].values
        high_arr = data["high"].values
        low_arr = data["low"].values
        atr_arr = (data["high"] - data["low"]).rolling(14, min_periods=1).mean().values
        ts_arr = data.index

    n = len(close_arr)
    entry_price = float(close_arr[i])
    atr = float(atr_arr[i])
    if atr != atr or atr <= 0:
        atr = entry_price * 0.005

    if direction == "LONG":
        sl = entry_price - sl_r * atr
        tp = entry_price + tp_r * atr
    else:
        sl = entry_price + sl_r * atr
        tp = entry_price - tp_r * atr

    exit_ts = ts_arr[i]
    exit_price = entry_price
    result = "TIMEOUT"

    for j in range(i + 1, n):
        lo, hi = low_arr[j], high_arr[j]
        if direction == "LONG":
            if lo <= sl:
                exit_price, result, exit_ts = sl, "LOSS", ts_arr[j]
                break
            if hi >= tp:
                exit_price, result, exit_ts = tp, "WIN", ts_arr[j]
                break
        else:
            if hi >= sl:
                exit_price, result, exit_ts = sl, "LOSS", ts_arr[j]
                break
            if lo <= tp:
                exit_price, result, exit_ts = tp, "WIN", ts_arr[j]
                break
        if j == n - 1:
            exit_price, exit_ts, result = float(close_arr[j]), ts_arr[j], "TIMEOUT"

    profit_usd = (exit_price - entry_price) if direction == "LONG" else (entry_price - exit_price)
    profit_r = calculate_rr(entry_price, exit_price, sl, direction)

    return {
        "entry_price": entry_price, "exit_price": exit_price, "sl": sl, "tp": tp,
        "exit_ts": exit_ts, "profit_usd": profit_usd, "profit_r": profit_r, "result": result, "atr": atr,
    }


def run_backtest(cfg: Dict[str, Any], precomputed_regime: Optional[pd.Series] = None) -> List[Trade]:
    """Run backtest with given config. Returns list of Trade objects."""
    symbol = cfg.get("symbol", "XAUUSD")
    timeframes = cfg.get("timeframes", ["15m"])
    tf = timeframes[0]
    base_path = Path(cfg.get("data", {}).get("base_path", "data/market_cache"))
    period_days = cfg.get("backtest", {}).get("default_period_days", 60)
    tp_r = cfg.get("backtest", {}).get("tp_r", 2.0)
    sl_r = cfg.get("backtest", {}).get("sl_r", 1.0)
    session_filter = cfg.get("backtest", {}).get("session_filter", None)
    session_mode = cfg.get("backtest", {}).get("session_mode", "killzone")

    risk_cfg = cfg.get("risk", {})
    max_daily_loss_r = risk_cfg.get("max_daily_loss_r", 3.0)
    equity_kill_switch_pct = risk_cfg.get("equity_kill_switch_pct", 10.0)

    end = datetime.now()
    start = end - timedelta(days=period_days)
    data = load_parquet(base_path, symbol, tf, start=start, end=end)
    if data.empty or len(data) < 50:
        data = ensure_data(symbol=symbol, timeframe=tf, base_path=base_path, period_days=period_days)
    if data.empty or len(data) < 50:
        logger.warning("No data available. Run fetch first.")
        return []

    data = data.sort_index()
    strategy_cfg = cfg.get("strategy", {}) or {}
    sqe_cfg = get_sqe_default_config()
    if strategy_cfg:
        _deep_merge(sqe_cfg, strategy_cfg)

    # Regime detection
    regime_series: Optional[pd.Series] = None
    if precomputed_regime is not None:
        regime_series = precomputed_regime.reindex(data.index, method="ffill")
        data["regime"] = regime_series
    else:
        try:
            from src.quantbuild.strategy_modules.regime.detector import RegimeDetector
            detector = RegimeDetector()
            data_1h = load_parquet(base_path, symbol, "1h", start=start, end=end)
            if not data_1h.empty:
                data_1h = data_1h.sort_index()
            regime_series = detector.classify(data, data_1h if not data_1h.empty else None)
            data["regime"] = regime_series
        except (ImportError, Exception) as e:
            logger.debug("Regime detection skipped: %s", e)

    # Generate entry signals
    precomputed_df = _compute_modules_once(data, sqe_cfg)
    long_entries = run_sqe_conditions(data, "LONG", sqe_cfg, _precomputed_df=precomputed_df)
    short_entries = run_sqe_conditions(data, "SHORT", sqe_cfg, _precomputed_df=precomputed_df)
    logger.info("LONG entries (pre-filter): %d | SHORT entries: %d", int(long_entries.sum()), int(short_entries.sum()))

    # H1 structure gate
    if strategy_cfg.get("structure_use_h1_gate", False) and "1h" in timeframes and tf != "1h":
        long_entries = _apply_h1_gate(long_entries, data, "LONG", base_path, symbol, start, end, sqe_cfg)
        short_entries = _apply_h1_gate(short_entries, data, "SHORT", base_path, symbol, start, end, sqe_cfg)

    # Session filtering
    allowed_sessions = session_filter or list(ENTRY_SESSIONS)
    if session_filter is not None:
        session_mask = data.index.map(lambda ts: session_from_timestamp(ts, mode=session_mode) in allowed_sessions)
        long_entries = long_entries & session_mask
        short_entries = short_entries & session_mask

    # Combine entries
    entry_signals = []
    for i in range(1, len(data) - 1):
        if long_entries.iloc[i]:
            entry_signals.append((i, "LONG"))
        if short_entries.iloc[i]:
            entry_signals.append((i, "SHORT"))

    # Risk management state
    max_trades_per_session = risk_cfg.get("max_trades_per_session", 1)
    traded_session_direction: Dict[Any, int] = {}
    daily_pnl_r: Dict[Any, float] = {}
    cumulative_r = 0.0
    peak_r = 0.0
    kill_switch_triggered = False
    trades: List[Trade] = []

    sim_cache = _prepare_sim_cache(data)

    for i, direction in entry_signals:
        entry_ts = data.index[i]
        trade_date = entry_ts.date()

        if kill_switch_triggered:
            break
        if daily_pnl_r.get(trade_date, 0.0) <= -max_daily_loss_r:
            continue
        if (peak_r - cumulative_r) >= equity_kill_switch_pct:
            kill_switch_triggered = True
            break

        session_key = (trade_date, session_from_timestamp(entry_ts, mode=session_mode), direction)
        if traded_session_direction.get(session_key, 0) >= max_trades_per_session:
            continue

        current_regime = None
        if regime_series is not None and i < len(regime_series):
            current_regime = regime_series.iloc[i]

        regime_cfg = cfg.get("regime_profiles", None)
        trade_tp_r, trade_sl_r = tp_r, sl_r
        if regime_cfg and current_regime is not None:
            regime_profile = regime_cfg.get(current_regime.lower(), {}) if isinstance(current_regime, str) else {}
            if regime_profile:
                trade_tp_r = regime_profile.get("tp_r", tp_r)
                trade_sl_r = regime_profile.get("sl_r", sl_r)

        result = _simulate_trade(data, i, direction, trade_tp_r, trade_sl_r, _cache=sim_cache)

        t = Trade(
            timestamp_open=entry_ts,
            timestamp_close=result["exit_ts"],
            symbol=symbol,
            direction=direction,
            entry_price=result["entry_price"],
            exit_price=result["exit_price"],
            sl=result["sl"],
            tp=result["tp"],
            profit_usd=result["profit_usd"],
            profit_r=result["profit_r"],
            result=result["result"],
            regime=str(current_regime) if current_regime else None,
        )
        traded_session_direction[session_key] = traded_session_direction.get(session_key, 0) + 1
        trades.append(t)

        cumulative_r += result["profit_r"]
        if cumulative_r > peak_r:
            peak_r = cumulative_r
        daily_pnl_r[trade_date] = daily_pnl_r.get(trade_date, 0.0) + result["profit_r"]

    logger.info("%s %s: %d trades (LONG: %d, SHORT: %d)", symbol, tf, len(trades),
                sum(1 for t in trades if t.direction == "LONG"),
                sum(1 for t in trades if t.direction == "SHORT"))

    if trades:
        from src.quantbuild.backtest.metrics import compute_metrics
        m = compute_metrics(trades)
        logger.info(
            "Result: net_pnl=%.2f pf=%.2f wr=%.1f%% dd=%.2fR n=%d",
            m.get("net_pnl", 0), m.get("profit_factor", 0),
            m.get("win_rate", 0), m.get("max_drawdown", 0), m.get("trade_count", 0),
        )
    return trades
