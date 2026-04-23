"""Backtest engine: load data, run strategy, record trades.

Supports:
  - Regime-aware entry filtering (TREND/EXPANSION/COMPRESSION)
  - Per-regime TP/SL/position-size profiles
  - NewsGate integration (block around events, sentiment boost)
  - NewsHistory replay for backtesting with historical news
"""
import logging
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

import numpy as np
import pandas as pd

from src.quantbuild.indicators.atr import atr as compute_atr
from src.quantbuild.models.trade import Trade, calculate_rr
from src.quantbuild.data.sessions import session_from_timestamp, ENTRY_SESSIONS
from src.quantbuild.io.parquet_loader import load_parquet, ensure_data
from src.quantbuild.strategies.sqe_xauusd import (
    run_sqe_conditions,
    get_sqe_default_config,
    _compute_modules_once,
    sqe_decision_context_at_bar,
)
from src.quantbuild.strategy_modules.ict.structure_context import add_structure_context
from src.quantbuild.execution.quantlog_emitter import QuantLogEmitter
from src.quantbuild.execution.quantlog_ids import resolve_quantlog_run_id, resolve_quantlog_session_id
from src.quantbuild.execution.quantlog_no_action import canonical_no_action_reason
from src.quantbuild.quantlog_repo import quantbuild_project_root, resolve_quantlog_repo_path
from src.quantbuild.execution.signal_evaluated_payload import (
    assert_signal_evaluated_payload_complete,
    build_signal_evaluated_payload,
    new_decision_cycle_id,
)
from src.quantbuild.policy.system_mode import bypassed_filters_vs_production, resolve_effective_filters

logger = logging.getLogger(__name__)


def _bar_timestamp_utc_iso(ts: Any) -> str:
    t = pd.Timestamp(ts)
    if t.tzinfo is None:
        t = t.tz_localize("UTC")
    else:
        t = t.tz_convert("UTC")
    return t.isoformat().replace("+00:00", "Z")


def _init_backtest_quantlog(cfg: Dict[str, Any]) -> Optional[QuantLogEmitter]:
    ql_cfg = cfg.get("quantlog", {}) or {}
    if not bool(ql_cfg.get("enabled", True)):
        return None
    raw = Path(str(ql_cfg.get("base_path", "data/quantlog_events")))
    ql_base = raw.resolve() if raw.is_absolute() else (quantbuild_project_root() / raw).resolve()
    ql_env = str(ql_cfg.get("environment", "backtest"))
    run_id = resolve_quantlog_run_id(ql_cfg)
    session_id = resolve_quantlog_session_id(ql_cfg)
    consolidated_raw = ql_cfg.get("consolidated_run_file")
    consolidated_path: Optional[Path] = None
    if consolidated_raw is True:
        consolidated_path = (ql_base / "runs" / f"{run_id}.jsonl").resolve()
    elif isinstance(consolidated_raw, str) and consolidated_raw.strip():
        raw_p = Path(consolidated_raw.strip())
        consolidated_path = (
            raw_p.resolve() if raw_p.is_absolute() else (quantbuild_project_root() / raw_p).resolve()
        )
    emitter = QuantLogEmitter(
        base_path=ql_base,
        source_component="backtest_engine",
        environment=ql_env,
        run_id=run_id,
        session_id=session_id,
        consolidated_path=consolidated_path,
    )
    if consolidated_path is not None:
        logger.info(
            "QuantLog emitter enabled (backtest): consolidated_run_file=%s run_id=%s",
            consolidated_path,
            run_id,
        )
    else:
        logger.info(
            "QuantLog emitter enabled (backtest): base_path=%s run_id=%s (resolved from repo root)",
            ql_base,
            run_id,
        )
    if resolve_quantlog_repo_path() is None:
        logger.warning(
            "QuantLog JSONL is on, but the QuantLog repository was not found for CLI "
            "(validate/summarize). Clone quantlog, set QUANTLOG_REPO_PATH or QUANTLOG_ROOT, or run "
            "python scripts/check_quantlog_linkage.py — events will still be written."
        )
    return emitter


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


def _exit_tag_from_simulator(sim_result: str) -> str:
    """Simulator outcome → compact exit tag for QuantLog / analytics (SL/TP/TIMEOUT)."""
    return {"LOSS": "SL", "WIN": "TP", "TIMEOUT": "TIMEOUT"}.get(str(sim_result).strip(), str(sim_result))


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
    bt_cfg = cfg.get("backtest", {}) or {}
    period_days = bt_cfg.get("default_period_days", 60)
    tp_r = bt_cfg.get("tp_r", 2.0)
    sl_r = bt_cfg.get("sl_r", 1.0)
    session_filter = bt_cfg.get("session_filter", None)
    session_mode = bt_cfg.get("session_mode", "killzone")

    risk_cfg = cfg.get("risk", {})
    max_daily_loss_r = risk_cfg.get("max_daily_loss_r", 3.0)
    equity_kill_switch_pct = risk_cfg.get("equity_kill_switch_pct", 10.0)
    base_max_trades_per_session = risk_cfg.get("max_trades_per_session", 1)

    system_mode, eff_f = resolve_effective_filters(cfg)
    bypassed_by_mode = bypassed_filters_vs_production(eff_f)
    logger.info(
        "Backtest system_mode=%s effective_filters=%s",
        system_mode,
        {k: eff_f[k] for k in sorted(eff_f)},
    )

    sd_raw = bt_cfg.get("start_date")
    ed_raw = bt_cfg.get("end_date")
    fetch_span_days = period_days

    if sd_raw and ed_raw:
        d0 = date.fromisoformat(str(sd_raw).strip()[:10])
        d1 = date.fromisoformat(str(ed_raw).strip()[:10])
        if d1 < d0:
            logger.warning("backtest end_date before start_date; swapping")
            d0, d1 = d1, d0
        start = datetime.combine(d0, time.min, tzinfo=timezone.utc)
        end = datetime.combine(d1, time.max, tzinfo=timezone.utc)
        fetch_span_days = max((d1 - d0).days + 60, period_days)
        logger.info(
            "Backtest fixed window (UTC): %s .. %s",
            start.isoformat(),
            end.isoformat(),
        )
    elif sd_raw or ed_raw:
        logger.warning(
            "backtest requires both start_date and end_date; ignoring partial — using rolling window"
        )
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=period_days)
    else:
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=period_days)

    data = load_parquet(base_path, symbol, tf, start=start, end=end)
    fixed_calendar_window = bool(sd_raw and ed_raw)
    if data.empty or len(data) < 50:
        # Fixed start/end backtests need history that spans the window. Auto-fetch via
        # ``ensure_data`` uses a single Dukascopy call that can return a short slice and
        # **overwrite** a longer parquet — never shrink cache that way.
        if not fixed_calendar_window:
            ensure_data(symbol=symbol, timeframe=tf, base_path=base_path, period_days=fetch_span_days)
            data = load_parquet(base_path, symbol, tf, start=start, end=end)
    if data.empty or len(data) < 50:
        if fixed_calendar_window:
            logger.warning(
                "No OHLC rows for backtest window %s .. %s (symbol=%s tf=%s base_path=%s). "
                "Prefetch long history without overwriting, e.g.: "
                "python scripts/fetch_dukascopy_xauusd.py --days 550 --tf 15m 1h",
                start.date(),
                end.date(),
                symbol,
                tf,
                base_path,
            )
        else:
            logger.warning("No data available. Run fetch first.")
        return []

    data = data.sort_index()
    strategy_cfg = cfg.get("strategy", {}) or {}
    sqe_cfg = get_sqe_default_config()
    if strategy_cfg:
        _deep_merge(sqe_cfg, strategy_cfg)
    else:
        logger.warning(
            "Backtest YAML has no `strategy:` section — using raw get_sqe_default_config() only. "
            "That preset is stricter than production (e.g. liquidity_levels.require_all=True, "
            "entry_sweep_disp_fvg_min_count->3 via code defaults), which often yields **zero** "
            "LONG/SHORT pre-filter signals. "
            "For prod-like SQE use configs/strict_prod_v2.yaml merged with your dates, "
            "or copy its `strategy:` (and usually `regime_profiles:`) blocks."
        )

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

    # H1 structure gate — runs before regime/session guards; EDGE_DISCOVERY defaults to skipping it
    wants_h1 = (
        strategy_cfg.get("structure_use_h1_gate", False)
        and "1h" in timeframes
        and tf != "1h"
    )
    if wants_h1 and eff_f.get("structure_h1_gate", True):
        long_entries = _apply_h1_gate(long_entries, data, "LONG", base_path, symbol, start, end, sqe_cfg)
        short_entries = _apply_h1_gate(short_entries, data, "SHORT", base_path, symbol, start, end, sqe_cfg)
    elif wants_h1:
        logger.info(
            "Skipping H1 structure gate (effective filter structure_h1_gate=false; typical for EDGE_DISCOVERY)"
        )

    # Session filtering (optional prefilter on bars — regime loop may add stricter rules)
    allowed_sessions = session_filter or list(ENTRY_SESSIONS)
    apply_session_prefilter = eff_f.get("session", True) and session_filter is not None
    if apply_session_prefilter:
        session_mask = data.index.map(
            lambda ts: session_from_timestamp(ts, mode=session_mode) in allowed_sessions
        )
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

    ql_emitter = _init_backtest_quantlog(cfg)
    account_id = str(cfg.get("broker", {}).get("account_id") or "backtest")
    strategy_id_bt = "sqe_backtest"

    for i, direction in entry_signals:
        if kill_switch_triggered:
            break

        entry_ts = data.index[i]
        trade_date = entry_ts.date()
        current_session = session_from_timestamp(entry_ts, mode=session_mode)

        current_regime = None
        if regime_series is not None and i < len(regime_series):
            current_regime = regime_series.iloc[i]
        regime_str = str(current_regime) if current_regime is not None else "none"

        trace_id = str(uuid4())
        decision_cycle_id = new_decision_cycle_id(prefix="dc_bt")
        signal_id = f"sig_bt_{trace_id.replace('-', '')[:16]}"
        ts_iso = _bar_timestamp_utc_iso(entry_ts)
        decision_ctx_at_bar = sqe_decision_context_at_bar(precomputed_df, direction, i, sqe_cfg)
        try:
            price_at_sig = float(data["close"].iloc[i])
        except (KeyError, TypeError, ValueError, IndexError):
            price_at_sig = None
        combo_n = decision_ctx_at_bar.get("combo_active_modules_count")

        def _emit_signal_evaluated() -> None:
            if not ql_emitter:
                return
            desk_bt: Dict[str, Any] = {}
            if combo_n is not None:
                try:
                    desk_bt["combo_count"] = int(combo_n)
                except (TypeError, ValueError):
                    pass
            if price_at_sig is not None:
                desk_bt["price_at_signal"] = price_at_sig
            se_payload = build_signal_evaluated_payload(
                decision_cycle_id=decision_cycle_id,
                session=current_session,
                regime=regime_str,
                signal_type="sqe_entry",
                signal_direction=direction,
                confidence=1.0,
                system_mode=system_mode,
                bypassed_by_mode=list(bypassed_by_mode),
                setup_type="sqe",
                setup=True,
                eval_stage="backtest_candidate",
                decision_context=None,
                desk_extra=desk_bt or None,
            )
            assert_signal_evaluated_payload_complete(se_payload)
            ql_emitter.emit(
                event_type="signal_evaluated",
                trace_id=trace_id,
                timestamp_utc=ts_iso,
                account_id=account_id,
                strategy_id=strategy_id_bt,
                symbol=symbol,
                decision_cycle_id=decision_cycle_id,
                payload=se_payload,
            )

        def _emit_signal_detected() -> None:
            if not ql_emitter:
                return
            ql_emitter.emit(
                event_type="signal_detected",
                trace_id=trace_id,
                timestamp_utc=ts_iso,
                account_id=account_id,
                strategy_id=strategy_id_bt,
                symbol=symbol,
                decision_cycle_id=decision_cycle_id,
                payload={
                    "signal_id": signal_id,
                    "type": "sqe_entry",
                    "direction": direction,
                    "strength": 1.0,
                    "bar_timestamp": ts_iso,
                    "session": current_session,
                    "regime": regime_str,
                    "modules": decision_ctx_at_bar,
                },
            )

        def _emit_blocked(internal_code: str, guard_name: str) -> None:
            if not ql_emitter:
                return
            eff = canonical_no_action_reason(internal_code)
            ql_emitter.emit(
                event_type="risk_guard_decision",
                trace_id=trace_id,
                timestamp_utc=ts_iso,
                account_id=account_id,
                strategy_id=strategy_id_bt,
                symbol=symbol,
                decision_cycle_id=decision_cycle_id,
                payload={
                    "guard_name": guard_name,
                    "decision": "BLOCK",
                    "reason": eff,
                    "session": current_session,
                    "regime": regime_str,
                },
            )
            ql_emitter.emit(
                event_type="trade_action",
                trace_id=trace_id,
                timestamp_utc=ts_iso,
                account_id=account_id,
                strategy_id=strategy_id_bt,
                symbol=symbol,
                decision_cycle_id=decision_cycle_id,
                payload={
                    "decision": "NO_ACTION",
                    "reason": eff,
                    "session": current_session,
                    "regime": regime_str,
                    "system_mode": system_mode,
                },
            )
            ql_emitter.emit(
                event_type="signal_filtered",
                trace_id=trace_id,
                timestamp_utc=ts_iso,
                account_id=account_id,
                strategy_id=strategy_id_bt,
                symbol=symbol,
                decision_cycle_id=decision_cycle_id,
                payload={
                    "signal_id": signal_id,
                    "filter_reason": eff,
                    "raw_reason": internal_code,
                    "detail": {"guard_name": guard_name},
                },
            )

        _emit_signal_detected()
        _emit_signal_evaluated()

        if eff_f.get("daily_loss", True) and daily_pnl_r.get(trade_date, 0.0) <= -max_daily_loss_r:
            _emit_blocked("daily_loss_block", "daily_loss_cap")
            continue
        if (peak_r - cumulative_r) >= equity_kill_switch_pct:
            _emit_blocked("risk_block", "equity_drawdown_kill_switch")
            kill_switch_triggered = True
            break

        regime_profile = {}
        if regime_profiles and current_regime is not None:
            regime_key = current_regime.lower() if isinstance(current_regime, str) else str(current_regime)
            regime_profile = regime_profiles.get(regime_key, {})

        if eff_f.get("regime", True) and regime_profile.get("skip", False):
            regime_skip_count += 1
            _emit_blocked("regime_block", "regime_profile")
            continue

        if eff_f.get("session", True):
            allowed_sessions = regime_profile.get("allowed_sessions")
            if allowed_sessions and current_session not in allowed_sessions:
                regime_session_skip_count += 1
                _emit_blocked("time_filter_block", "regime_allowed_sessions")
                continue

            min_hour = regime_profile.get("min_hour_utc")
            if min_hour is not None and entry_ts.hour < min_hour:
                regime_session_skip_count += 1
                _emit_blocked("time_filter_block", "regime_min_hour_utc")
                continue

            max_hour = regime_profile.get("max_hour_utc")
            if max_hour is not None and entry_ts.hour >= max_hour:
                regime_session_skip_count += 1
                _emit_blocked("time_filter_block", "regime_max_hour_utc")
                continue

        max_tps = regime_profile.get("max_trades_per_session", base_max_trades_per_session)
        session_key = (trade_date, current_session, direction)
        if eff_f.get("position_limit", True) and traded_session_direction.get(session_key, 0) >= max_tps:
            _emit_blocked("position_limit_block", "max_trades_per_session")
            continue

        news_boost = 1.0
        news_sentiment_at_entry = None
        if news_gate is not None and eff_f.get("news", True):
            gate_result = news_gate.check_gate(entry_ts, direction)
            if not gate_result["allowed"]:
                news_block_count += 1
                _emit_blocked("news_block", "news_gate")
                continue
            news_boost = gate_result.get("boost", 1.0)

        if _news_history is not None:
            sentiment_at = _news_history.get_sentiment_at(entry_ts)
            if sentiment_at:
                news_sentiment_at_entry = sentiment_at.get("direction")

        trade_tp_r = regime_profile.get("tp_r", tp_r)
        trade_sl_r = regime_profile.get("sl_r", sl_r)

        result = _simulate_trade(data, i, direction, trade_tp_r, trade_sl_r, _cache=sim_cache)

        size_mult = float(regime_profile.get("position_size_mult", 1.0)) * float(news_boost)
        if abs(size_mult - 1.0) > 1e-12:
            result = dict(result)
            result["profit_r"] = float(result["profit_r"]) * size_mult
            result["profit_usd"] = float(result["profit_usd"]) * size_mult
            result["mae_r"] = float(result["mae_r"]) * size_mult
            result["mfe_r"] = float(result["mfe_r"]) * size_mult

        trade_ref = f"BT-{trace_id[:8]}"
        sim_vol = float(risk_cfg.get("backtest_sim_volume_lots", 1.0))
        if ql_emitter:
            ql_emitter.emit(
                event_type="risk_guard_decision",
                trace_id=trace_id,
                timestamp_utc=ts_iso,
                account_id=account_id,
                strategy_id=strategy_id_bt,
                symbol=symbol,
                decision_cycle_id=decision_cycle_id,
                payload={
                    "guard_name": "backtest_pipeline",
                    "decision": "ALLOW",
                    "reason": "simulated_execution",
                },
            )
            ql_emitter.emit(
                event_type="trade_action",
                trace_id=trace_id,
                timestamp_utc=ts_iso,
                account_id=account_id,
                strategy_id=strategy_id_bt,
                symbol=symbol,
                decision_cycle_id=decision_cycle_id,
                payload={
                    "decision": "ENTER",
                    "reason": "all_conditions_met",
                    "side": direction,
                    "session": current_session,
                    "regime": regime_str,
                    "system_mode": system_mode,
                    "trade_id": trade_ref,
                },
            )
            ql_emitter.emit(
                event_type="order_submitted",
                trace_id=trace_id,
                timestamp_utc=ts_iso,
                account_id=account_id,
                strategy_id=strategy_id_bt,
                symbol=symbol,
                order_ref=trade_ref,
                decision_cycle_id=decision_cycle_id,
                payload={
                    "order_ref": trade_ref,
                    "side": direction,
                    "volume": sim_vol,
                    "trade_id": trade_ref,
                    "decision_cycle_id": decision_cycle_id,
                },
            )
            ql_emitter.emit(
                event_type="order_filled",
                trace_id=trace_id,
                timestamp_utc=ts_iso,
                account_id=account_id,
                strategy_id=strategy_id_bt,
                symbol=symbol,
                order_ref=trade_ref,
                decision_cycle_id=decision_cycle_id,
                payload={
                    "order_ref": trade_ref,
                    "fill_price": float(result["entry_price"]),
                    "trade_id": trade_ref,
                    "decision_cycle_id": decision_cycle_id,
                },
            )
            tex_dir = "LONG" if str(direction).upper() in ("LONG", "BUY") else "SHORT"
            ql_emitter.emit(
                event_type="trade_executed",
                trace_id=trace_id,
                timestamp_utc=ts_iso,
                account_id=account_id,
                strategy_id=strategy_id_bt,
                symbol=symbol,
                order_ref=trade_ref,
                decision_cycle_id=decision_cycle_id,
                payload={
                    "signal_id": signal_id,
                    "direction": tex_dir,
                    "trade_id": trade_ref,
                    "session": current_session,
                    "regime": regime_str,
                    "decision_cycle_id": decision_cycle_id,
                },
            )
            exit_ts_iso = _bar_timestamp_utc_iso(result["exit_ts"])
            ql_emitter.emit(
                event_type="trade_closed",
                trace_id=trace_id,
                timestamp_utc=exit_ts_iso,
                account_id=account_id,
                strategy_id=strategy_id_bt,
                symbol=symbol,
                order_ref=trade_ref,
                decision_cycle_id=decision_cycle_id,
                payload={
                    "trade_id": trade_ref,
                    "order_ref": trade_ref,
                    "direction": tex_dir,
                    "exit_price": float(result["exit_price"]),
                    "pnl_abs": float(result["profit_usd"]),
                    "pnl_r": float(result["profit_r"]),
                    "mae_r": float(result["mae_r"]),
                    "mfe_r": float(result["mfe_r"]),
                    "outcome": result["result"],
                    "exit": _exit_tag_from_simulator(result["result"]),
                    "session": current_session,
                    "regime": regime_str,
                    "decision_cycle_id": decision_cycle_id,
                },
            )

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

    run_metrics: Optional[Dict[str, Any]] = None
    if trades:
        from src.quantbuild.backtest.metrics import compute_metrics

        run_metrics = compute_metrics(trades)
        logger.info(
            "Result: net_pnl=%.2f pf=%.2f wr=%.1f%% dd=%.2fR n=%d",
            run_metrics.get("net_pnl", 0),
            run_metrics.get("profit_factor", 0),
            run_metrics.get("win_rate", 0),
            run_metrics.get("max_drawdown", 0),
            run_metrics.get("trade_count", 0),
        )

    try:
        from src.quantbuild.integration.quantanalytics_post_run import invoke_quantanalytics_after_quantlog
        from src.quantbuild.integration.quantos_artifacts import invoke_collect_run_artifacts

        invoke_quantanalytics_after_quantlog(cfg, ql_emitter)
        invoke_collect_run_artifacts(cfg, ql_emitter)
    except Exception:
        logger.debug("QuantAnalytics/QuantOS post-run hook skipped after exception", exc_info=True)

    return trades
