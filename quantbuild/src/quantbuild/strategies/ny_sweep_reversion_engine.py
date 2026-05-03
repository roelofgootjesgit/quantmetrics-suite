"""
Dedicated NY Sweep Reversion backtest engine.

Consumes merged research YAML (configs/experiments/ny_sweep_reversion/*.yaml) referenced from
QuantBuild config via ``backtest.engine: ny_sweep_reversion`` and
``backtest.ny_sweep_reversion_config`` (path). Resolves ``QUANTMETRICS_SUITE_ROOT`` for relative paths.

v1 scope: London high/low (UTC), sweep → displacement → bullish/bearish FVG, limit fill at FVG
midpoint within expiry bars, SL at sweep extreme ± buffer, exit via fixed-R multiple from research
``take_profit`` when ``model: fixed_r``. Partials / BE are not simulated in v1.
"""
from __future__ import annotations

import logging
import os
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

import numpy as np
import pandas as pd

from src.quantbuild.backtest.engine import (
    _bar_timestamp_utc_iso,
    _deep_merge,
    _exit_tag_from_simulator,
    _init_backtest_quantlog,
    _prepare_sim_cache,
    _setup_news_gate,
    _simulate_trade_price_levels,
)
from src.quantbuild.export.trade_r_series import (
    assert_quantlog_inference_policy,
    maybe_write_trade_r_series_fallback,
)
from src.quantbuild.execution.signal_evaluated_payload import (
    assert_signal_evaluated_payload_complete,
    build_signal_evaluated_payload,
    new_decision_cycle_id,
)
from src.quantbuild.config import _load_yaml_with_extends
from src.quantbuild.data.sessions import session_from_timestamp
from src.quantbuild.indicators.atr import atr as compute_atr
from src.quantbuild.io.parquet_loader import load_parquet
from src.quantbuild.models.trade import Trade
from src.quantbuild.policy.system_mode import bypassed_filters_vs_production, resolve_effective_filters
from src.quantbuild.strategy_modules.ict.structure_context import add_structure_context
logger = logging.getLogger(__name__)

# Max M15 bars after sweep bar to find displacement + FVG (wider = more chances, more overlap risk)
MAX_CHAIN_BARS = 40


def _regime_str(df: pd.DataFrame, i: int, regime_series: Optional[pd.Series]) -> str:
    if regime_series is not None and i < len(regime_series):
        v = regime_series.iloc[i]
        if v is None or (isinstance(v, float) and not np.isfinite(v)):
            return "none"
        return str(v)
    if "regime" in df.columns:
        v = df["regime"].iloc[i]
        if pd.isna(v):
            return "none"
        return str(v)
    return "none"


def _emit_setup_candidate(
    ql_emitter: Optional[Any],
    funnel_logging: bool,
    *,
    ts: Any,
    df: pd.DataFrame,
    i: int,
    session_mode: str,
    regime_series: Optional[pd.Series],
    account_id: str,
    strategy_id: str,
    symbol: str,
    l_hi: float,
    l_lo: float,
) -> None:
    if not funnel_logging or ql_emitter is None:
        return
    ts_iso = _bar_timestamp_utc_iso(ts)
    ql_emitter.emit(
        event_type="setup_candidate",
        trace_id=str(uuid4()),
        timestamp_utc=ts_iso,
        account_id=account_id,
        strategy_id=strategy_id,
        symbol=symbol,
        payload={
            "timestamp_utc": ts_iso,
            "session": session_from_timestamp(ts, mode=session_mode),
            "regime": _regime_str(df, i, regime_series),
            "london_high": float(l_hi),
            "london_low": float(l_lo),
        },
    )


def _emit_setup_rejected(
    ql_emitter: Optional[Any],
    funnel_logging: bool,
    *,
    ts: Any,
    df: pd.DataFrame,
    i: int,
    session_mode: str,
    regime_series: Optional[pd.Series],
    account_id: str,
    strategy_id: str,
    symbol: str,
    reason: str,
) -> None:
    if not funnel_logging or ql_emitter is None:
        return
    ts_iso = _bar_timestamp_utc_iso(ts)
    ql_emitter.emit(
        event_type="setup_rejected",
        trace_id=str(uuid4()),
        timestamp_utc=ts_iso,
        account_id=account_id,
        strategy_id=strategy_id,
        symbol=symbol,
        payload={
            "timestamp_utc": ts_iso,
            "session": session_from_timestamp(ts, mode=session_mode),
            "regime": _regime_str(df, i, regime_series),
            "reason": reason,
        },
    )


def resolve_ny_sweep_spec_path(cfg: Dict[str, Any]) -> Path:
    bt = cfg.get("backtest") or {}
    raw = bt.get("ny_sweep_reversion_config") or (cfg.get("ny_sweep_reversion") or {}).get("spec_path")
    if not raw:
        raise ValueError(
            "Set backtest.ny_sweep_reversion_config (or ny_sweep_reversion.spec_path) to a merged YAML."
        )
    p = Path(str(raw).strip())
    if p.is_file():
        return p.resolve()
    suite = os.environ.get("QUANTMETRICS_SUITE_ROOT")
    if suite:
        cand = (Path(suite).resolve() / str(raw).strip().lstrip("/\\")).resolve()
        if cand.is_file():
            return cand
    qb = Path(__file__).resolve().parents[3]  # quantbuild/src/quantbuild/strategies -> quantbuild
    cand2 = qb / raw
    if cand2.is_file():
        return cand2.resolve()
    cand3 = Path.cwd() / raw
    if cand3.is_file():
        return cand3.resolve()
    raise FileNotFoundError(f"NY sweep spec YAML not found: {raw}")


def load_ny_sweep_spec(cfg: Dict[str, Any]) -> Dict[str, Any]:
    path = resolve_ny_sweep_spec_path(cfg)
    return _load_yaml_with_extends(path, set())


def _parse_hhmm(s: str) -> Tuple[int, int]:
    parts = str(s).strip().split(":")
    h = int(parts[0])
    m = int(parts[1]) if len(parts) > 1 else 0
    return h, m


def _minute_of_day(ts: Any) -> int:
    t = pd.Timestamp(ts)
    if t.tzinfo is None:
        t = t.tz_localize("UTC")
    else:
        t = t.tz_convert("UTC")
    return int(t.hour * 60 + t.minute)


def _in_hhmm_window(ts: Any, start_str: str, end_str: str) -> bool:
    sh, sm = _parse_hhmm(start_str)
    eh, em = _parse_hhmm(end_str)
    lo = sh * 60 + sm
    hi = eh * 60 + em
    m = _minute_of_day(ts)
    return lo <= m <= hi


def _build_london_levels(df: pd.DataFrame, start_str: str, end_str: str) -> Dict[date, Tuple[float, float]]:
    out: Dict[date, Tuple[float, float]] = {}
    for d, grp in df.groupby(df.index.date):
        mask = np.array([_in_hhmm_window(ts, start_str, end_str) for ts in grp.index])
        if not mask.any():
            continue
        sub = grp.loc[mask]
        out[d] = (float(sub["high"].max()), float(sub["low"].min()))
    return out


def _displacement_ok(
    row: pd.Series,
    atr_val: float,
    min_body_ratio: float,
    min_range_atr: float,
) -> bool:
    o = float(row["open"])
    h, l, c = float(row["high"]), float(row["low"]), float(row["close"])
    body = abs(c - o)
    rng = h - l
    if rng <= 0 or not np.isfinite(atr_val) or atr_val <= 0:
        return False
    if body / rng < min_body_ratio:
        return False
    if rng < min_range_atr * atr_val:
        return False
    return True


def _tp_price(entry: float, sl: float, direction: str, spec: Dict[str, Any]) -> float:
    tp_cfg = spec.get("take_profit") or {}
    model = str(tp_cfg.get("model", "fixed_r")).lower()
    if model == "partials":
        # v1: use tp1 distance as full exit proxy when partials only
        r = float((tp_cfg.get("tp1") or {}).get("r_multiple", 1.5))
    else:
        r = float(tp_cfg.get("r_multiple", 2.0))
    risk = abs(entry - sl)
    if direction == "LONG":
        return entry + r * risk
    return entry - r * risk


def discover_setups(
    df: pd.DataFrame,
    spec: Dict[str, Any],
    h1_long: Optional[pd.Series],
    h1_short: Optional[pd.Series],
    *,
    ql_emitter: Optional[Any] = None,
    funnel_logging: bool = False,
    symbol: str = "",
    account_id: str = "backtest",
    strategy_id: str = "ny_sweep_reversion",
    regime_series: Optional[pd.Series] = None,
    session_mode: str = "extended",
) -> List[Dict[str, Any]]:
    sessions = spec.get("sessions") or {}
    london = sessions.get("london_reference") or {}
    trade_win = sessions.get("trade_allowed_window") or {}

    su = spec.get("setup") or {}
    sw_cfg = su.get("sweep") or {}
    dp_cfg = su.get("displacement") or {}
    fvg_cfg = su.get("fair_value_gap") or {}

    if not sw_cfg.get("enabled", True):
        return []

    london_start = str(london.get("start_utc", "07:00"))
    london_end = str(london.get("end_utc", "12:00"))
    tr_start = str(trade_win.get("start_utc", "13:30"))
    tr_end = str(trade_win.get("end_utc", "15:30"))
    # Where the London sweep may occur: default = full trade window (not the narrow ny_setup sub-window)
    sweep_search = sessions.get("sweep_search_window") or trade_win
    sw_start = str(sweep_search.get("start_utc", tr_start))
    sw_end = str(sweep_search.get("end_utc", tr_end))

    buf = float((spec.get("stop_loss") or {}).get("buffer_points", 5.0))
    atr_period = int(dp_cfg.get("atr_period", 14))
    min_body = float(dp_cfg.get("min_body_to_range_ratio", 0.70))
    min_rng_atr = float(dp_cfg.get("min_range_atr_multiple", 1.50))
    min_gap_pts = float(fvg_cfg.get("min_gap_points", 5.0))
    req_after_disp = bool(fvg_cfg.get("require_after_displacement", True))
    expire_bars = int((spec.get("entry") or {}).get("expire_if_not_filled_bars", 4))

    bias_on = bool(((spec.get("bias") or {}).get("h1_structure") or {}).get("enabled", True))

    atr_s = compute_atr(df, period=atr_period)
    london_by_date = _build_london_levels(df, london_start, london_end)

    signals: List[Dict[str, Any]] = []
    n = len(df)
    highs = df["high"].values
    lows = df["low"].values
    closes = df["close"].values

    for i in range(2, n):
        ts_i = df.index[i]
        if not _in_hhmm_window(ts_i, sw_start, sw_end):
            continue
        d = ts_i.date() if hasattr(ts_i, "date") else pd.Timestamp(ts_i).date()
        if d not in london_by_date:
            continue
        l_hi, l_lo = london_by_date[d]

        _emit_setup_candidate(
            ql_emitter,
            funnel_logging,
            ts=ts_i,
            df=df,
            i=i,
            session_mode=session_mode,
            regime_series=regime_series,
            account_id=account_id,
            strategy_id=strategy_id,
            symbol=symbol,
            l_hi=l_hi,
            l_lo=l_lo,
        )

        chain_end = min(i + MAX_CHAIN_BARS, n)

        long_ok = lows[i] < l_lo and closes[i] > l_lo
        short_ok = highs[i] > l_hi and closes[i] < l_hi

        # LONG: sweep London low
        if long_ok:
            if bias_on and h1_long is not None and not bool(h1_long.iloc[i]):
                _emit_setup_rejected(
                    ql_emitter,
                    funnel_logging,
                    ts=ts_i,
                    df=df,
                    i=i,
                    session_mode=session_mode,
                    regime_series=regime_series,
                    account_id=account_id,
                    strategy_id=strategy_id,
                    symbol=symbol,
                    reason="h1_bias",
                )
                continue
            sweep_low = float(lows[i])
            # displacement then FVG
            d_bar = None
            for j in range(i, chain_end):
                if not _in_hhmm_window(df.index[j], tr_start, tr_end):
                    continue
                if _displacement_ok(df.iloc[j], float(atr_s.iloc[j]), min_body, min_rng_atr):
                    d_bar = j
                    break
            if d_bar is None:
                _emit_setup_rejected(
                    ql_emitter,
                    funnel_logging,
                    ts=ts_i,
                    df=df,
                    i=i,
                    session_mode=session_mode,
                    regime_series=regime_series,
                    account_id=account_id,
                    strategy_id=strategy_id,
                    symbol=symbol,
                    reason="no_displacement",
                )
                continue

            f_bar = None
            gap_lo = gap_hi = None
            start_f = d_bar if req_after_disp else i
            for j in range(max(start_f, 2), chain_end):
                if not _in_hhmm_window(df.index[j], tr_start, tr_end):
                    continue
                if j < 2:
                    continue
                # Bullish FVG at j: low[j] > high[j-2]
                if lows[j] > highs[j - 2]:
                    g_lo, g_hi = float(highs[j - 2]), float(lows[j])
                    if g_hi - g_lo >= min_gap_pts:
                        f_bar = j
                        gap_lo, gap_hi = g_lo, g_hi
                        break
            if f_bar is None or gap_lo is None:
                _emit_setup_rejected(
                    ql_emitter,
                    funnel_logging,
                    ts=ts_i,
                    df=df,
                    i=i,
                    session_mode=session_mode,
                    regime_series=regime_series,
                    account_id=account_id,
                    strategy_id=strategy_id,
                    symbol=symbol,
                    reason="no_fvg",
                )
                continue

            mid = 0.5 * (gap_lo + gap_hi)
            sl = sweep_low - buf
            # invalidation + fill
            filled_at = None
            invalidated = False
            for k in range(f_bar + 1, min(f_bar + 1 + expire_bars, n)):
                if not _in_hhmm_window(df.index[k], tr_start, tr_end):
                    continue
                # close outside FVG zone → cancel
                c_ = float(closes[k])
                if c_ < gap_lo or c_ > gap_hi:
                    filled_at = None
                    invalidated = True
                    break
                lo_, hi_ = float(lows[k]), float(highs[k])
                if lo_ <= mid <= hi_:
                    filled_at = k
                    break
            if filled_at is None:
                _emit_setup_rejected(
                    ql_emitter,
                    funnel_logging,
                    ts=ts_i,
                    df=df,
                    i=i,
                    session_mode=session_mode,
                    regime_series=regime_series,
                    account_id=account_id,
                    strategy_id=strategy_id,
                    symbol=symbol,
                    reason="fill_invalidated" if invalidated else "fill_expired",
                )
                continue

            entry_price = mid
            tp_px = _tp_price(entry_price, sl, "LONG", spec)
            signals.append(
                {
                    "entry_idx": filled_at,
                    "direction": "LONG",
                    "entry_price": entry_price,
                    "sl_price": sl,
                    "tp_price": tp_px,
                    "setup_bar": i,
                }
            )

        elif short_ok:
            if bias_on and h1_short is not None and not bool(h1_short.iloc[i]):
                _emit_setup_rejected(
                    ql_emitter,
                    funnel_logging,
                    ts=ts_i,
                    df=df,
                    i=i,
                    session_mode=session_mode,
                    regime_series=regime_series,
                    account_id=account_id,
                    strategy_id=strategy_id,
                    symbol=symbol,
                    reason="h1_bias",
                )
                continue
            sweep_hi = float(highs[i])
            d_bar = None
            for j in range(i, chain_end):
                if not _in_hhmm_window(df.index[j], tr_start, tr_end):
                    continue
                if _displacement_ok(df.iloc[j], float(atr_s.iloc[j]), min_body, min_rng_atr):
                    d_bar = j
                    break
            if d_bar is None:
                _emit_setup_rejected(
                    ql_emitter,
                    funnel_logging,
                    ts=ts_i,
                    df=df,
                    i=i,
                    session_mode=session_mode,
                    regime_series=regime_series,
                    account_id=account_id,
                    strategy_id=strategy_id,
                    symbol=symbol,
                    reason="no_displacement",
                )
                continue

            f_bar = None
            gap_lo = gap_hi = None
            start_f = d_bar if req_after_disp else i
            for j in range(max(start_f, 2), chain_end):
                if not _in_hhmm_window(df.index[j], tr_start, tr_end):
                    continue
                # Bearish FVG at j: high[j] < low[j-2]
                if highs[j] < lows[j - 2]:
                    g_lo, g_hi = float(highs[j]), float(lows[j - 2])
                    if g_hi - g_lo >= min_gap_pts:
                        f_bar = j
                        gap_lo, gap_hi = g_lo, g_hi
                        break
            if f_bar is None or gap_lo is None:
                _emit_setup_rejected(
                    ql_emitter,
                    funnel_logging,
                    ts=ts_i,
                    df=df,
                    i=i,
                    session_mode=session_mode,
                    regime_series=regime_series,
                    account_id=account_id,
                    strategy_id=strategy_id,
                    symbol=symbol,
                    reason="no_fvg",
                )
                continue

            mid = 0.5 * (gap_lo + gap_hi)
            sl = sweep_hi + buf

            filled_at = None
            invalidated = False
            for k in range(f_bar + 1, min(f_bar + 1 + expire_bars, n)):
                if not _in_hhmm_window(df.index[k], tr_start, tr_end):
                    continue
                c_ = float(closes[k])
                if c_ > gap_hi or c_ < gap_lo:
                    filled_at = None
                    invalidated = True
                    break
                lo_, hi_ = float(lows[k]), float(highs[k])
                if lo_ <= mid <= hi_:
                    filled_at = k
                    break
            if filled_at is None:
                _emit_setup_rejected(
                    ql_emitter,
                    funnel_logging,
                    ts=ts_i,
                    df=df,
                    i=i,
                    session_mode=session_mode,
                    regime_series=regime_series,
                    account_id=account_id,
                    strategy_id=strategy_id,
                    symbol=symbol,
                    reason="fill_invalidated" if invalidated else "fill_expired",
                )
                continue

            entry_price = mid
            tp_px = _tp_price(entry_price, sl, "SHORT", spec)
            signals.append(
                {
                    "entry_idx": filled_at,
                    "direction": "SHORT",
                    "entry_price": entry_price,
                    "sl_price": sl,
                    "tp_price": tp_px,
                    "setup_bar": i,
                }
            )

        else:
            _emit_setup_rejected(
                ql_emitter,
                funnel_logging,
                ts=ts_i,
                df=df,
                i=i,
                session_mode=session_mode,
                regime_series=regime_series,
                account_id=account_id,
                strategy_id=strategy_id,
                symbol=symbol,
                reason="no_sweep",
            )

    signals.sort(key=lambda x: x["entry_idx"])
    return signals


def run_ny_sweep_backtest(
    cfg: Dict[str, Any],
    data: pd.DataFrame,
    start: datetime,
    end: datetime,
    base_path: Path,
    symbol: str,
    tf: str,
    regime_series: Optional[pd.Series],
) -> List[Trade]:
    """Execute NY sweep pipeline for bars already loaded (M15)."""
    bt_cfg = cfg.get("backtest", {}) or {}
    risk_cfg = cfg.get("risk", {})
    max_daily_loss_r = risk_cfg.get("max_daily_loss_r", 3.0)
    equity_kill_switch_pct = risk_cfg.get("equity_kill_switch_pct", 10.0)
    session_mode = bt_cfg.get("session_mode", "extended")

    system_mode, eff_f = resolve_effective_filters(cfg)
    bypassed_by_mode = bypassed_filters_vs_production(eff_f)

    spec = load_ny_sweep_spec(cfg)
    deep = cfg.get("ny_sweep_reversion") or {}
    if isinstance(deep, dict) and deep.get("overrides"):
        _deep_merge(spec, deep["overrides"])

    df = data.sort_index()

    df_1h = load_parquet(base_path, symbol, "1h", start=start, end=end)
    if not df_1h.empty:
        df_1h = df_1h.sort_index()
    struct_cfg = {"lookback": 30, "pivot_bars": 2}
    h1_long = h1_short = None
    bias_on = bool(((spec.get("bias") or {}).get("h1_structure") or {}).get("enabled", True))
    if bias_on and not df_1h.empty:
        df_1h_ctx = add_structure_context(df_1h.copy(), struct_cfg)
        h1_long = df_1h_ctx["in_bullish_structure"].reindex(df.index, method="ffill").fillna(False)
        h1_short = df_1h_ctx["in_bearish_structure"].reindex(df.index, method="ffill").fillna(False)

    funnel_logging = bool(deep.get("funnel_logging", True)) if isinstance(deep, dict) else True
    account_id = str(cfg.get("broker", {}).get("account_id") or "backtest")
    strategy_id_bt = "ny_sweep_reversion"
    ql_emitter = _init_backtest_quantlog(cfg)
    assert_quantlog_inference_policy(cfg)
    funnel_on = funnel_logging and ql_emitter is not None

    raw_signals = discover_setups(
        df,
        spec,
        h1_long,
        h1_short,
        ql_emitter=ql_emitter,
        funnel_logging=funnel_on,
        symbol=symbol,
        account_id=account_id,
        strategy_id=strategy_id_bt,
        regime_series=regime_series,
        session_mode=session_mode,
    )
    logger.info("NY sweep raw setups: %d", len(raw_signals))

    max_per_day = int((spec.get("risk") or {}).get("max_trades_per_day", 2))
    stop_streak = int((spec.get("risk") or {}).get("stop_after_consecutive_losses", 99))

    def _utc_calendar_day(ts: Any) -> date:
        t = pd.Timestamp(ts)
        if t.tzinfo is None:
            t = t.tz_localize("UTC")
        else:
            t = t.tz_convert("UTC")
        return t.date()

    news_gate, _news_history = _setup_news_gate(cfg)
    sim_cache = _prepare_sim_cache(df)

    trades: List[Trade] = []
    trade_order_refs: List[str] = []
    daily_pnl_r: Dict[Any, float] = {}
    daily_trades: Dict[date, int] = {}
    cumulative_r = 0.0
    peak_r = 0.0
    kill_switch_triggered = False
    last_exit_bar = -1
    consec_loss = 0
    news_block_count = 0
    skip_overlap = 0
    skip_daily_cap = 0
    skip_consec = 0
    skip_daily_loss = 0

    for sig in raw_signals:
        if kill_switch_triggered:
            break
        i = int(sig["entry_idx"])
        direction = str(sig["direction"])
        entry_ts = df.index[i]
        trade_date = _utc_calendar_day(entry_ts)
        if i <= last_exit_bar:
            skip_overlap += 1
            _emit_setup_rejected(
                ql_emitter,
                funnel_on,
                ts=entry_ts,
                df=df,
                i=i,
                session_mode=session_mode,
                regime_series=regime_series,
                account_id=account_id,
                strategy_id=strategy_id_bt,
                symbol=symbol,
                reason="overlap",
            )
            continue
        if daily_trades.get(trade_date, 0) >= max_per_day:
            skip_daily_cap += 1
            _emit_setup_rejected(
                ql_emitter,
                funnel_on,
                ts=entry_ts,
                df=df,
                i=i,
                session_mode=session_mode,
                regime_series=regime_series,
                account_id=account_id,
                strategy_id=strategy_id_bt,
                symbol=symbol,
                reason="daily_cap",
            )
            continue
        if consec_loss >= stop_streak:
            skip_consec += 1
            _emit_setup_rejected(
                ql_emitter,
                funnel_on,
                ts=entry_ts,
                df=df,
                i=i,
                session_mode=session_mode,
                regime_series=regime_series,
                account_id=account_id,
                strategy_id=strategy_id_bt,
                symbol=symbol,
                reason="consecutive_loss",
            )
            continue

        current_session = session_from_timestamp(entry_ts, mode=session_mode)

        current_regime = None
        if regime_series is not None and i < len(regime_series):
            current_regime = regime_series.iloc[i]
        regime_str = str(current_regime) if current_regime is not None else "none"

        if eff_f.get("daily_loss", True) and daily_pnl_r.get(trade_date, 0.0) <= -max_daily_loss_r:
            skip_daily_loss += 1
            _emit_setup_rejected(
                ql_emitter,
                funnel_on,
                ts=entry_ts,
                df=df,
                i=i,
                session_mode=session_mode,
                regime_series=regime_series,
                account_id=account_id,
                strategy_id=strategy_id_bt,
                symbol=symbol,
                reason="daily_loss",
            )
            continue
        if (peak_r - cumulative_r) >= equity_kill_switch_pct:
            kill_switch_triggered = True
            break

        if news_gate is not None and eff_f.get("news", True) and cfg.get("news", {}).get("enabled", False):
            gate_result = news_gate.check_gate(entry_ts, direction)
            if not gate_result.get("allowed", True):
                news_block_count += 1
                _emit_setup_rejected(
                    ql_emitter,
                    funnel_on,
                    ts=entry_ts,
                    df=df,
                    i=i,
                    session_mode=session_mode,
                    regime_series=regime_series,
                    account_id=account_id,
                    strategy_id=strategy_id_bt,
                    symbol=symbol,
                    reason="news",
                )
                continue

        entry_price = float(sig["entry_price"])
        sl_price = float(sig["sl_price"])
        tp_price = float(sig["tp_price"])

        trace_id = str(uuid4())
        decision_cycle_id = new_decision_cycle_id(prefix="dc_bt")
        signal_id = f"sig_ny_{trace_id.replace('-', '')[:16]}"
        ts_iso = _bar_timestamp_utc_iso(entry_ts)

        result = _simulate_trade_price_levels(df, i, direction, entry_price, sl_price, tp_price, _cache=sim_cache)
        last_exit_bar = int(result.get("exit_bar_idx", i))

        trade_ref = f"BT-{trace_id[:8]}"
        sim_vol = float(risk_cfg.get("backtest_sim_volume_lots", 1.0))
        tex_dir = "LONG" if str(direction).upper() in ("LONG", "BUY") else "SHORT"

        if ql_emitter:
            desk_extra = {
                "engine": "ny_sweep_reversion",
                "setup_bar_index": int(sig.get("setup_bar", -1)),
                "entry_price_limit": entry_price,
            }
            se_payload = build_signal_evaluated_payload(
                decision_cycle_id=decision_cycle_id,
                session=current_session,
                regime=regime_str,
                signal_type="ny_sweep_entry",
                signal_direction=direction,
                confidence=1.0,
                system_mode=system_mode,
                bypassed_by_mode=list(bypassed_by_mode),
                setup_type="ny_sweep_reversion",
                setup=True,
                eval_stage="backtest_candidate",
                decision_context=None,
                desk_extra=desk_extra,
            )
            assert_signal_evaluated_payload_complete(se_payload)
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
                    "type": "ny_sweep_entry",
                    "direction": direction,
                    "strength": 1.0,
                    "bar_timestamp": ts_iso,
                    "session": current_session,
                    "regime": regime_str,
                    "modules": desk_extra,
                },
            )
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
                    "decision": "ENTER",
                    "reason": "ny_sweep_reversion",
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
            regime=regime_str,
            session=current_session,
        )
        trades.append(t)
        trade_order_refs.append(trade_ref)
        daily_trades[trade_date] = daily_trades.get(trade_date, 0) + 1
        pr = float(result["profit_r"])
        daily_pnl_r[trade_date] = daily_pnl_r.get(trade_date, 0.0) + pr
        cumulative_r += pr
        if cumulative_r > peak_r:
            peak_r = cumulative_r
        if pr < 0:
            consec_loss += 1
        else:
            consec_loss = 0

    logger.info(
        "%s %s NY sweep: %d trades (LONG: %d, SHORT: %d); max %d fills per UTC day | "
        "skipped: overlap=%d daily_cap=%d consec_loss=%d daily_loss=%d",
        symbol,
        tf,
        len(trades),
        sum(1 for t in trades if t.direction == "LONG"),
        sum(1 for t in trades if t.direction == "SHORT"),
        max_per_day,
        skip_overlap,
        skip_daily_cap,
        skip_consec,
        skip_daily_loss,
    )
    metrics_out: Optional[Dict[str, Any]] = None
    if trades:
        from src.quantbuild.backtest.metrics import compute_metrics

        m = compute_metrics(trades)
        metrics_out = dict(m)
        logger.info(
            "NY sweep result: net_pnl=%.2f pf=%.2f wr=%.1f%% dd=%.2fR n=%d",
            m.get("net_pnl", 0),
            m.get("profit_factor", 0),
            m.get("win_rate", 0),
            m.get("max_drawdown", 0),
            m.get("trade_count", 0),
        )

    maybe_write_trade_r_series_fallback(cfg, trades, trade_order_refs)

    try:
        from src.quantbuild.integration.quantanalytics_post_run import invoke_quantanalytics_after_quantlog
        from src.quantbuild.integration.quantos_artifacts import invoke_collect_run_artifacts
        from src.quantbuild.integration.quantresearch_runs import invoke_quantresearch_run_bundle

        invoke_quantanalytics_after_quantlog(cfg, ql_emitter)
        invoke_collect_run_artifacts(cfg, ql_emitter)
        invoke_quantresearch_run_bundle(cfg, ql_emitter, metrics_out)
    except Exception:
        logger.debug("QuantAnalytics post-run skipped", exc_info=True)

    return trades
