"""Backtest engine: load data, run strategy, record trades.

Supports:
  - Regime-aware entry filtering (TREND/EXPANSION/COMPRESSION)
  - Per-regime TP/SL/position-size profiles
  - NewsGate integration (block around events, sentiment boost)
  - NewsHistory replay for backtesting with historical news
"""
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from src.quantbuild.indicators.atr import atr as compute_atr
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
        "atr": compute_atr(data, period=14).values.astype(np.float64),
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
    max_favorable = 0.0
    max_adverse = 0.0

    for j in range(i + 1, n):
        lo, hi = low_arr[j], high_arr[j]

        if direction == "LONG":
            favorable = hi - entry_price
            adverse = entry_price - lo
            if lo <= sl:
                exit_price, result, exit_ts = sl, "LOSS", ts_arr[j]
                max_adverse = max(max_adverse, adverse)
                break
            if hi >= tp:
                exit_price, result, exit_ts = tp, "WIN", ts_arr[j]
                max_favorable = max(max_favorable, favorable)
                break
        else:
            favorable = entry_price - lo
            adverse = hi - entry_price
            if hi >= sl:
                exit_price, result, exit_ts = sl, "LOSS", ts_arr[j]
                max_adverse = max(max_adverse, adverse)
                break
            if lo <= tp:
                exit_price, result, exit_ts = tp, "WIN", ts_arr[j]
                max_favorable = max(max_favorable, favorable)
                break

        max_favorable = max(max_favorable, favorable)
        max_adverse = max(max_adverse, adverse)

        if j == n - 1:
            exit_price, exit_ts, result = float(close_arr[j]), ts_arr[j], "TIMEOUT"

    risk = abs(entry_price - sl)
    mae_r = (max_adverse / risk) if risk else 0.0
    mfe_r = (max_favorable / risk) if risk else 0.0
    profit_usd = (exit_price - entry_price) if direction == "LONG" else (entry_price - exit_price)
    profit_r = calculate_rr(entry_price, exit_price, sl, direction)

    return {
        "entry_price": entry_price, "exit_price": exit_price, "sl": sl, "tp": tp,
        "exit_ts": exit_ts, "profit_usd": profit_usd, "profit_r": profit_r,
        "result": result, "atr": atr, "mae_r": mae_r, "mfe_r": mfe_r,
    }


def _setup_news_gate(cfg: Dict[str, Any]):
    """Initialize NewsGate + NewsHistory for backtest if news is enabled."""
    if not cfg.get("news", {}).get("enabled", False):
        return None, None

    try:
        from src.quantbuild.strategy_modules.news_gate import NewsGate
        from src.quantbuild.news.history import NewsHistory

        gate = NewsGate(cfg)
        history = NewsHistory()
        loaded = history.load_from_parquet()
        if loaded > 0:
            logger.info("NewsGate active with %d historical events", loaded)
            for ev in history.events:
                sentiment = None
                if ev.event_id in history._sentiments:
                    sentiment = history._sentiments[ev.event_id]
                gate.add_news_event(ev, sentiment)
        else:
            logger.info("NewsGate active but no historical news data (passthrough mode)")
        return gate, history
    except Exception as e:
        logger.debug("NewsGate setup skipped: %s", e)
        return None, None


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
    base_max_trades_per_session = risk_cfg.get("max_trades_per_session", 1)

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
    regime_profiles = cfg.get("regime_profiles", None)
    if precomputed_regime is not None:
        regime_series = precomputed_regime.reindex(data.index, method="ffill")
        data["regime"] = regime_series
    else:
        try:
            from src.quantbuild.strategy_modules.regime.detector import RegimeDetector
            regime_cfg = cfg.get("regime", {})
            detector = RegimeDetector(config=regime_cfg)
            data_1h = load_parquet(base_path, symbol, "1h", start=start, end=end)
            if not data_1h.empty:
                data_1h = data_1h.sort_index()
            regime_series = detector.classify(data, data_1h if not data_1h.empty else None)
            data["regime"] = regime_series
        except (ImportError, Exception) as e:
            logger.debug("Regime detection skipped: %s", e)

    # NewsGate setup (loads historical news if available)
    news_gate, _news_history = _setup_news_gate(cfg)

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
    traded_session_direction: Dict[Any, int] = {}
    daily_pnl_r: Dict[Any, float] = {}
    cumulative_r = 0.0
    peak_r = 0.0
    kill_switch_triggered = False
    trades: List[Trade] = []
    regime_skip_count = 0
    regime_session_skip_count = 0
    news_block_count = 0

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

        # Regime-aware filtering
        current_regime = None
        regime_profile: Dict[str, Any] = {}
        if regime_series is not None and i < len(regime_series):
            current_regime = regime_series.iloc[i]
            if regime_profiles and current_regime is not None:
                regime_key = current_regime.lower() if isinstance(current_regime, str) else str(current_regime)
                regime_profile = regime_profiles.get(regime_key, {})

        if regime_profile.get("skip", False):
            regime_skip_count += 1
            continue

        # Per-regime session + time-of-day filter
        current_session = session_from_timestamp(entry_ts, mode=session_mode)
        allowed_sessions = regime_profile.get("allowed_sessions")
        if allowed_sessions and current_session not in allowed_sessions:
            regime_session_skip_count += 1
            continue

        min_hour = regime_profile.get("min_hour_utc")
        if min_hour is not None and entry_ts.hour < min_hour:
            regime_session_skip_count += 1
            continue

        max_hour = regime_profile.get("max_hour_utc")
        if max_hour is not None and entry_ts.hour >= max_hour:
            regime_session_skip_count += 1
            continue

        # Per-regime max trades per session
        max_tps = regime_profile.get("max_trades_per_session", base_max_trades_per_session)
        session_key = (trade_date, current_session, direction)
        if traded_session_direction.get(session_key, 0) >= max_tps:
            continue

        # NewsGate check
        news_boost = 1.0
        news_sentiment_at_entry = None
        if news_gate is not None:
            gate_result = news_gate.check_gate(entry_ts, direction)
            if not gate_result["allowed"]:
                news_block_count += 1
                continue
            news_boost = gate_result.get("boost", 1.0)

        if _news_history is not None:
            sentiment_at = _news_history.get_sentiment_at(entry_ts)
            if sentiment_at:
                news_sentiment_at_entry = sentiment_at.get("direction")

        # Regime-aware TP/SL
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
            session=current_session,
            news_sentiment_at_entry=news_sentiment_at_entry,
            news_boost_applied=news_boost if news_boost != 1.0 else None,
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
    if regime_skip_count:
        logger.info("Regime skipped: %d entries (COMPRESSION)", regime_skip_count)
    if regime_session_skip_count:
        logger.info("Regime-session filtered: %d entries", regime_session_skip_count)
    if news_block_count:
        logger.info("NewsGate blocked: %d entries", news_block_count)

    if trades:
        from src.quantbuild.backtest.metrics import compute_metrics
        m = compute_metrics(trades)
        logger.info(
            "Result: net_pnl=%.2f pf=%.2f wr=%.1f%% dd=%.2fR n=%d",
            m.get("net_pnl", 0), m.get("profit_factor", 0),
            m.get("win_rate", 0), m.get("max_drawdown", 0), m.get("trade_count", 0),
        )
    return trades
