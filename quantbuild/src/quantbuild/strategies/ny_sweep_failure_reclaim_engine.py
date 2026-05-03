"""
HYP-002 — NY Sweep Failure Reclaim (dedicated backtest engine).

Hypothese staat los van HYP-001 (`ny_sweep_reversion_engine`): sweep zonder same-bar reclaim,
classificatie via continuation-diepte over N bars, entry op reclaim-close binnen M bars.
Geen displacement/FVG in v1.0-run — alleen frequentie- en richting-pad naar vaste-R simulatie.
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
from src.quantbuild.config import _load_yaml_with_extends
from src.quantbuild.data.sessions import session_from_timestamp
from src.quantbuild.execution.signal_evaluated_payload import (
    assert_signal_evaluated_payload_complete,
    build_signal_evaluated_payload,
    new_decision_cycle_id,
)
from src.quantbuild.io.parquet_loader import load_parquet
from src.quantbuild.models.trade import Trade, calculate_rr
from src.quantbuild.policy.system_mode import bypassed_filters_vs_production, resolve_effective_filters

logger = logging.getLogger(__name__)

HYPOTHESIS_ID = "HYP-002"
STRATEGY_ID = "ny_sweep_failure_reclaim"


def _variant_id(spec: Dict[str, Any]) -> str:
    v = spec.get("variant") or {}
    if isinstance(v, dict) and v.get("id"):
        return str(v["id"]).strip()
    return ""


def _overlap_shadow_enabled(spec: Dict[str, Any]) -> bool:
    ex = spec.get("execution") or {}
    return str(ex.get("overlap_policy", "")).strip().lower() == "block_and_shadow_log"


def _apply_mock_spread_to_sim_result(
    result: Dict[str, Any],
    direction: str,
    mock_spread: float,
) -> Dict[str, Any]:
    """Conservative half-spread on entry only: LONG fills at entry+spread/2, SHORT at entry-spread/2."""
    spread = float(mock_spread or 0.0)
    if spread <= 0:
        return result
    d_u = str(direction).upper()
    is_long = "LONG" in d_u or d_u == "BUY"
    entry = float(result["entry_price"])
    exit_p = float(result["exit_price"])
    sl = float(result["sl"])
    if is_long:
        adj_e = entry + spread / 2.0
        new_r = calculate_rr(adj_e, exit_p, sl, "LONG")
        new_usd = exit_p - adj_e
    else:
        adj_e = entry - spread / 2.0
        new_r = calculate_rr(adj_e, exit_p, sl, "SHORT")
        new_usd = adj_e - exit_p
    out = dict(result)
    out["profit_r"] = new_r
    out["profit_usd"] = new_usd
    return out


def _regime_excluded_for_trade(spec: Dict[str, Any], regime: str) -> bool:
    rf = spec.get("regime_filter") or {}
    raw = rf.get("exclude") or []
    excl = {str(x).strip().lower() for x in raw if x is not None}
    return regime.strip().lower() in excl


def resolve_hyp002_spec_path(cfg: Dict[str, Any]) -> Path:
    bt = cfg.get("backtest") or {}
    raw = bt.get("ny_sweep_failure_reclaim_config") or (cfg.get("ny_sweep_failure_reclaim") or {}).get(
        "spec_path"
    )
    if not raw:
        raise ValueError(
            "Set backtest.ny_sweep_failure_reclaim_config (or ny_sweep_failure_reclaim.spec_path) "
            "to HYP-002 spec.yaml."
        )
    p = Path(str(raw).strip())
    if p.is_file():
        return p.resolve()
    suite = os.environ.get("QUANTMETRICS_SUITE_ROOT")
    if suite:
        cand = (Path(suite).resolve() / str(raw).strip().lstrip("/\\")).resolve()
        if cand.is_file():
            return cand
    qb = Path(__file__).resolve().parents[3]
    cand2 = qb / raw
    if cand2.is_file():
        return cand2.resolve()
    cand3 = Path.cwd() / raw
    if cand3.is_file():
        return cand3.resolve()
    raise FileNotFoundError(f"HYP-002 spec YAML not found: {raw}")


def load_hyp002_spec(cfg: Dict[str, Any]) -> Dict[str, Any]:
    return _load_yaml_with_extends(resolve_hyp002_spec_path(cfg), set())


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


def _tp_price(entry: float, sl: float, direction: str, spec: Dict[str, Any]) -> float:
    tp_cfg = spec.get("take_profit") or {}
    model = str(tp_cfg.get("model", "fixed_r")).lower()
    if model == "partials":
        r = float((tp_cfg.get("tp1") or {}).get("r_multiple", 1.5))
    else:
        r = float(tp_cfg.get("r_multiple", 2.0))
    risk = abs(entry - sl)
    if direction == "LONG":
        return entry + r * risk
    return entry - r * risk


def _emit_setup_rejected_hyp002(
    ql_emitter: Optional[Any],
    *,
    ts: Any,
    df: pd.DataFrame,
    i: int,
    session_mode: str,
    regime_series: Optional[pd.Series],
    account_id: str,
    symbol: str,
    reason: str,
    sweep_id: Optional[str],
    variant_id: str = "",
) -> None:
    """Execution-skip na ``reclaim_entry_signal`` — zelfde event-type als HYP-001 funnel."""
    if ql_emitter is None:
        return
    ts_iso = _bar_timestamp_utc_iso(ts)
    pl: Dict[str, Any] = {
        "reason": reason,
        "sweep_id": sweep_id,
        "hypothesis": HYPOTHESIS_ID,
        "session": session_from_timestamp(ts, mode=session_mode),
        "regime": _regime_str(df, i, regime_series),
        "timestamp_utc": ts_iso,
    }
    if variant_id:
        pl["variant"] = variant_id
    ql_emitter.emit(
        event_type="setup_rejected",
        trace_id=str(uuid4()),
        timestamp_utc=ts_iso,
        account_id=account_id,
        strategy_id=STRATEGY_ID,
        symbol=symbol,
        payload=pl,
    )


def _emit_shadow_signal(
    ql_emitter: Optional[Any],
    *,
    ts: Any,
    df: pd.DataFrame,
    i: int,
    session_mode: str,
    regime_series: Optional[pd.Series],
    account_id: str,
    symbol: str,
    sweep_id: Optional[str],
    direction_lower: str,
    theoretical_entry_price: float,
    blocked_reason: str,
    variant_id: str,
    shadow_outcome: Optional[Dict[str, Any]] = None,
) -> None:
    if ql_emitter is None:
        return
    ts_iso = _bar_timestamp_utc_iso(ts)
    pl: Dict[str, Any] = {
        "sweep_id": sweep_id,
        "timestamp_utc": ts_iso,
        "direction": direction_lower,
        "theoretical_entry_price": float(theoretical_entry_price),
        "session": session_from_timestamp(ts, mode=session_mode),
        "regime": _regime_str(df, i, regime_series),
        "blocked_reason": blocked_reason,
        "hypothesis": HYPOTHESIS_ID,
    }
    if variant_id:
        pl["variant"] = variant_id
    if shadow_outcome:
        pl.update(shadow_outcome)
    ql_emitter.emit(
        event_type="shadow_signal",
        trace_id=str(uuid4()),
        timestamp_utc=ts_iso,
        account_id=account_id,
        strategy_id=STRATEGY_ID,
        symbol=symbol,
        payload=pl,
    )


def _emit_setup_candidate(
    ql_emitter: Any,
    *,
    ts: Any,
    df: pd.DataFrame,
    i: int,
    session_mode: str,
    regime_series: Optional[pd.Series],
    account_id: str,
    symbol: str,
    l_hi: float,
    l_lo: float,
) -> None:
    if ql_emitter is None:
        return
    ts_iso = _bar_timestamp_utc_iso(ts)
    ql_emitter.emit(
        event_type="setup_candidate",
        trace_id=str(uuid4()),
        timestamp_utc=ts_iso,
        account_id=account_id,
        strategy_id=STRATEGY_ID,
        symbol=symbol,
        payload={
            "timestamp_utc": ts_iso,
            "session": session_from_timestamp(ts, mode=session_mode),
            "regime": _regime_str(df, i, regime_series),
            "london_high": float(l_hi),
            "london_low": float(l_lo),
            "hypothesis": HYPOTHESIS_ID,
        },
    )


def discover_failure_reclaim_signals(
    df: pd.DataFrame,
    spec: Dict[str, Any],
    *,
    ql_emitter: Optional[Any],
    session_mode: str,
    regime_series: Optional[pd.Series],
    account_id: str,
    symbol: str,
) -> List[Dict[str, Any]]:
    """Scan M15 bars; emit setup_candidate, sweep_detected, sweep_classified, reclaim_entry_signal; return trade signals."""
    params = spec.get("parameters") or {}
    c_max = float(params.get("c_max_continuation_points", 5.0))
    n_fail = int(params.get("n_failure_window_bars", 3))
    m_rec = int(params.get("m_reclaim_window_bars", 6))

    sessions = spec.get("sessions") or {}
    london = sessions.get("london_reference") or {}
    trade_win = sessions.get("trade_allowed_window") or {}
    london_start = str(london.get("start_utc", "07:00"))
    london_end = str(london.get("end_utc", "12:00"))
    sw_start = str(trade_win.get("start_utc", "13:30"))
    sw_end = str(trade_win.get("end_utc", "16:00"))

    buf = float((spec.get("stop_loss") or {}).get("buffer_points", 5.0))
    london_by_date = _build_london_levels(df, london_start, london_end)

    n = len(df)
    highs = df["high"].values
    lows = df["low"].values
    closes = df["close"].values

    signals: List[Dict[str, Any]] = []

    for i in range(n):
        ts_i = df.index[i]
        if not _in_hhmm_window(ts_i, sw_start, sw_end):
            continue
        d = ts_i.date() if hasattr(ts_i, "date") else pd.Timestamp(ts_i).date()
        if d not in london_by_date:
            continue
        l_hi, l_lo = london_by_date[d]

        _emit_setup_candidate(
            ql_emitter,
            ts=ts_i,
            df=df,
            i=i,
            session_mode=session_mode,
            regime_series=regime_series,
            account_id=account_id,
            symbol=symbol,
            l_hi=l_hi,
            l_lo=l_lo,
        )

        long_sweep = bool(lows[i] < l_lo)
        short_sweep = bool(highs[i] > l_hi)
        if not long_sweep and not short_sweep:
            continue
        # Zeldzame dubbele sweep op één bar: verwerk alleen long (documentatie-keuze).
        if long_sweep:
            _process_sweep_bar(
                df,
                i,
                "long",
                l_hi,
                l_lo,
                c_max,
                n_fail,
                m_rec,
                buf,
                spec,
                ql_emitter,
                session_mode,
                regime_series,
                account_id,
                symbol,
                signals,
            )
        elif short_sweep:
            _process_sweep_bar(
                df,
                i,
                "short",
                l_hi,
                l_lo,
                c_max,
                n_fail,
                m_rec,
                buf,
                spec,
                ql_emitter,
                session_mode,
                regime_series,
                account_id,
                symbol,
                signals,
            )

    signals.sort(key=lambda x: int(x["entry_idx"]))
    return signals


def _process_sweep_bar(
    df: pd.DataFrame,
    i: int,
    direction: str,
    l_hi: float,
    l_lo: float,
    c_max: float,
    n_fail: int,
    m_rec: int,
    buf: float,
    spec: Dict[str, Any],
    ql_emitter: Optional[Any],
    session_mode: str,
    regime_series: Optional[pd.Series],
    account_id: str,
    symbol: str,
    signals: List[Dict[str, Any]],
) -> None:
    n = len(df)
    highs = df["high"].values
    lows = df["low"].values
    closes = df["close"].values

    sweep_id = str(uuid4())
    ts_sweep = df.index[i]
    ts_iso_sweep = _bar_timestamp_utc_iso(ts_sweep)
    london_level = float(l_lo) if direction == "long" else float(l_hi)
    if direction == "long":
        penetration = float(l_lo - lows[i])
    else:
        penetration = float(highs[i] - l_hi)

    if ql_emitter is not None:
        ql_emitter.emit(
            event_type="sweep_detected",
            trace_id=str(uuid4()),
            timestamp_utc=ts_iso_sweep,
            account_id=account_id,
            strategy_id=STRATEGY_ID,
            symbol=symbol,
            payload={
                "sweep_id": sweep_id,
                "timestamp_utc": ts_iso_sweep,
                "direction": direction,
                "london_level": london_level,
                "penetration_points": penetration,
                "session": session_from_timestamp(ts_sweep, mode=session_mode),
                "regime": _regime_str(df, i, regime_series),
                "hypothesis": HYPOTHESIS_ID,
            },
        )

    if i + 1 >= n:
        if ql_emitter is not None:
            ql_emitter.emit(
                event_type="sweep_classified",
                trace_id=str(uuid4()),
                timestamp_utc=ts_iso_sweep,
                account_id=account_id,
                strategy_id=STRATEGY_ID,
                symbol=symbol,
                payload={
                    "sweep_id": sweep_id,
                    "timestamp_utc": ts_iso_sweep,
                    "result": "inconclusive",
                    "max_continuation_points": 0.0,
                    "bars_evaluated": 0,
                    "reclaim_within_window": False,
                    "bars_to_reclaim": None,
                    "session": session_from_timestamp(ts_sweep, mode=session_mode),
                    "regime": _regime_str(df, i, regime_series),
                    "hypothesis": HYPOTHESIS_ID,
                },
            )
        return

    max_cont = 0.0
    bars_evaluated = 0
    for j in range(i + 1, min(i + 1 + n_fail, n)):
        bars_evaluated += 1
        if direction == "long":
            if lows[j] < l_lo:
                max_cont = max(max_cont, float(l_lo - lows[j]))
        else:
            if highs[j] > l_hi:
                max_cont = max(max_cont, float(highs[j] - l_hi))

    class_idx = min(i + n_fail, n - 1)
    ts_class = df.index[class_idx]
    ts_iso_class = _bar_timestamp_utc_iso(ts_class)

    result: str
    reclaim_within = False
    bars_to_reclaim: Optional[int] = None
    first_reclaim_k: Optional[int] = None

    if max_cont > c_max:
        result = "continuation"
    else:
        for k in range(i + 1, min(i + 1 + m_rec, n)):
            if direction == "long":
                if closes[k] > l_lo:
                    first_reclaim_k = k
                    break
            else:
                if closes[k] < l_hi:
                    first_reclaim_k = k
                    break
        if first_reclaim_k is not None:
            result = "failure"
            reclaim_within = True
            bars_to_reclaim = int(first_reclaim_k - i)
        else:
            result = "inconclusive"

    if ql_emitter is not None:
        ql_emitter.emit(
            event_type="sweep_classified",
            trace_id=str(uuid4()),
            timestamp_utc=ts_iso_class,
            account_id=account_id,
            strategy_id=STRATEGY_ID,
            symbol=symbol,
            payload={
                "sweep_id": sweep_id,
                "timestamp_utc": ts_iso_class,
                "result": result,
                "max_continuation_points": float(max_cont),
                "bars_evaluated": int(bars_evaluated),
                "reclaim_within_window": reclaim_within,
                "bars_to_reclaim": bars_to_reclaim,
                "session": session_from_timestamp(ts_class, mode=session_mode),
                "regime": _regime_str(df, class_idx, regime_series),
                "hypothesis": HYPOTHESIS_ID,
            },
        )

    if result != "failure" or first_reclaim_k is None:
        return

    k = first_reclaim_k
    entry_price = float(closes[k])
    ts_reclaim = df.index[k]
    ts_iso_reclaim = _bar_timestamp_utc_iso(ts_reclaim)
    trade_dir = "LONG" if direction == "long" else "SHORT"
    if direction == "long":
        sl_price = float(lows[i]) - buf
        tp_price = _tp_price(entry_price, sl_price, "LONG", spec)
    else:
        sl_price = float(highs[i]) + buf
        tp_price = _tp_price(entry_price, sl_price, "SHORT", spec)

    if ql_emitter is not None:
        ql_emitter.emit(
            event_type="reclaim_entry_signal",
            trace_id=str(uuid4()),
            timestamp_utc=ts_iso_reclaim,
            account_id=account_id,
            strategy_id=STRATEGY_ID,
            symbol=symbol,
            payload={
                "sweep_id": sweep_id,
                "timestamp_utc": ts_iso_reclaim,
                "direction": direction,
                "entry_price": entry_price,
                "session": session_from_timestamp(ts_reclaim, mode=session_mode),
                "regime": _regime_str(df, k, regime_series),
                "bars_since_sweep": int(k - i),
                "hypothesis": HYPOTHESIS_ID,
            },
        )

    signals.append(
        {
            "entry_idx": k,
            "direction": trade_dir,
            "entry_price": entry_price,
            "sl_price": sl_price,
            "tp_price": tp_price,
            "sweep_id": sweep_id,
            "setup_bar": i,
        }
    )


def run_ny_sweep_failure_reclaim_backtest(
    cfg: Dict[str, Any],
    data: pd.DataFrame,
    start: datetime,
    end: datetime,
    base_path: Path,
    symbol: str,
    tf: str,
    regime_series: Optional[pd.Series],
) -> List[Trade]:
    bt_cfg = cfg.get("backtest", {}) or {}
    risk_cfg = cfg.get("risk", {})
    max_daily_loss_r = risk_cfg.get("max_daily_loss_r", 3.0)
    equity_kill_switch_pct = risk_cfg.get("equity_kill_switch_pct", 10.0)
    session_mode = bt_cfg.get("session_mode", "extended")

    system_mode, eff_f = resolve_effective_filters(cfg)
    bypassed_by_mode = bypassed_filters_vs_production(eff_f)

    spec = load_hyp002_spec(cfg)
    deep = cfg.get("ny_sweep_failure_reclaim") or {}
    if isinstance(deep, dict) and deep.get("overrides"):
        _deep_merge(spec, deep["overrides"])

    df = data.sort_index()

    account_id = str(cfg.get("broker", {}).get("account_id") or "backtest")
    ql_emitter = _init_backtest_quantlog(cfg)

    raw_signals = discover_failure_reclaim_signals(
        df,
        spec,
        ql_emitter=ql_emitter,
        session_mode=session_mode,
        regime_series=regime_series,
        account_id=account_id,
        symbol=symbol,
    )
    logger.info("HYP-002 raw entry signals: %d", len(raw_signals))

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
    variant_id = _variant_id(spec)
    broker_cfg = cfg.get("broker") or {}
    mock_spread = float(broker_cfg.get("mock_spread") or 0.0)
    if mock_spread > 0:
        logger.info("HYP-002 mock_spread (entry half-spread R-adjust): %.4f", mock_spread)

    trades: List[Trade] = []
    daily_pnl_r: Dict[Any, float] = {}
    daily_trades: Dict[date, int] = {}
    cumulative_r = 0.0
    peak_r = 0.0
    kill_switch_triggered = False
    last_exit_bar = -1
    consec_loss = 0

    for sig in raw_signals:
        i = int(sig["entry_idx"])
        direction = str(sig["direction"])
        entry_ts = df.index[i]
        trade_date = _utc_calendar_day(entry_ts)
        sweep_id_sig = str(sig.get("sweep_id") or "")

        if kill_switch_triggered:
            _emit_setup_rejected_hyp002(
                ql_emitter,
                ts=entry_ts,
                df=df,
                i=i,
                session_mode=session_mode,
                regime_series=regime_series,
                account_id=account_id,
                symbol=symbol,
                reason="equity_kill_switch",
                sweep_id=sweep_id_sig or None,
                variant_id=variant_id,
            )
            continue

        if i <= last_exit_bar:
            if _overlap_shadow_enabled(spec):
                d_u = str(direction).upper()
                dir_lo = "long" if "LONG" in d_u or d_u == "BUY" else "short"
                entry_px = float(sig["entry_price"])
                sl_px = float(sig["sl_price"])
                tp_px = float(sig["tp_price"])
                sh_sim = _simulate_trade_price_levels(
                    df, i, direction, entry_px, sl_px, tp_px, _cache=sim_cache
                )
                sh_sim = _apply_mock_spread_to_sim_result(sh_sim, direction, mock_spread)
                rsim = str(sh_sim.get("result", "TIMEOUT")).upper()
                exit_tag = {"WIN": "TP", "LOSS": "SL", "TIMEOUT": "OPEN"}.get(rsim, "OPEN")
                shadow_outcome = {
                    "theoretical_sl_price": sl_px,
                    "theoretical_tp_price": tp_px,
                    "theoretical_outcome_r": float(sh_sim.get("profit_r", 0.0)),
                    "theoretical_exit_tag": exit_tag,
                    "theoretical_bars_to_exit": int(sh_sim.get("exit_bar_idx", i)) - i,
                }
                _emit_shadow_signal(
                    ql_emitter,
                    ts=entry_ts,
                    df=df,
                    i=i,
                    session_mode=session_mode,
                    regime_series=regime_series,
                    account_id=account_id,
                    symbol=symbol,
                    sweep_id=sweep_id_sig or None,
                    direction_lower=dir_lo,
                    theoretical_entry_price=entry_px,
                    blocked_reason="overlap",
                    variant_id=variant_id,
                    shadow_outcome=shadow_outcome,
                )
            _emit_setup_rejected_hyp002(
                ql_emitter,
                ts=entry_ts,
                df=df,
                i=i,
                session_mode=session_mode,
                regime_series=regime_series,
                account_id=account_id,
                symbol=symbol,
                reason="overlap",
                sweep_id=sweep_id_sig or None,
                variant_id=variant_id,
            )
            continue
        if daily_trades.get(trade_date, 0) >= max_per_day:
            _emit_setup_rejected_hyp002(
                ql_emitter,
                ts=entry_ts,
                df=df,
                i=i,
                session_mode=session_mode,
                regime_series=regime_series,
                account_id=account_id,
                symbol=symbol,
                reason="daily_cap",
                sweep_id=sweep_id_sig or None,
                variant_id=variant_id,
            )
            continue
        if consec_loss >= stop_streak:
            _emit_setup_rejected_hyp002(
                ql_emitter,
                ts=entry_ts,
                df=df,
                i=i,
                session_mode=session_mode,
                regime_series=regime_series,
                account_id=account_id,
                symbol=symbol,
                reason="consecutive_loss",
                sweep_id=sweep_id_sig or None,
                variant_id=variant_id,
            )
            continue

        current_session = session_from_timestamp(entry_ts, mode=session_mode)
        current_regime = None
        if regime_series is not None and i < len(regime_series):
            current_regime = regime_series.iloc[i]
        regime_str = str(current_regime) if current_regime is not None else "none"

        if _regime_excluded_for_trade(spec, regime_str):
            _emit_setup_rejected_hyp002(
                ql_emitter,
                ts=entry_ts,
                df=df,
                i=i,
                session_mode=session_mode,
                regime_series=regime_series,
                account_id=account_id,
                symbol=symbol,
                reason="regime_excluded",
                sweep_id=sweep_id_sig or None,
                variant_id=variant_id,
            )
            continue

        if eff_f.get("daily_loss", True) and daily_pnl_r.get(trade_date, 0.0) <= -max_daily_loss_r:
            _emit_setup_rejected_hyp002(
                ql_emitter,
                ts=entry_ts,
                df=df,
                i=i,
                session_mode=session_mode,
                regime_series=regime_series,
                account_id=account_id,
                symbol=symbol,
                reason="daily_loss",
                sweep_id=sweep_id_sig or None,
                variant_id=variant_id,
            )
            continue
        if (
            equity_kill_switch_pct is not None
            and float(equity_kill_switch_pct) > 0.0
            and (peak_r - cumulative_r) >= float(equity_kill_switch_pct)
        ):
            kill_switch_triggered = True
            _emit_setup_rejected_hyp002(
                ql_emitter,
                ts=entry_ts,
                df=df,
                i=i,
                session_mode=session_mode,
                regime_series=regime_series,
                account_id=account_id,
                symbol=symbol,
                reason="equity_kill_switch",
                sweep_id=sweep_id_sig or None,
                variant_id=variant_id,
            )
            continue

        if news_gate is not None and eff_f.get("news", True) and cfg.get("news", {}).get("enabled", False):
            gate_result = news_gate.check_gate(entry_ts, direction)
            if not gate_result.get("allowed", True):
                _emit_setup_rejected_hyp002(
                    ql_emitter,
                    ts=entry_ts,
                    df=df,
                    i=i,
                    session_mode=session_mode,
                    regime_series=regime_series,
                    account_id=account_id,
                    symbol=symbol,
                    reason="news",
                    sweep_id=sweep_id_sig or None,
                    variant_id=variant_id,
                )
                continue

        entry_price = float(sig["entry_price"])
        sl_price = float(sig["sl_price"])
        tp_price = float(sig["tp_price"])

        trace_id = str(uuid4())
        decision_cycle_id = new_decision_cycle_id(prefix="dc_bt")
        signal_id = f"sig_h2_{trace_id.replace('-', '')[:16]}"
        ts_iso = _bar_timestamp_utc_iso(entry_ts)

        result = _simulate_trade_price_levels(df, i, direction, entry_price, sl_price, tp_price, _cache=sim_cache)
        result = _apply_mock_spread_to_sim_result(result, direction, mock_spread)
        last_exit_bar = int(result.get("exit_bar_idx", i))

        trade_ref = f"BT-{trace_id[:8]}"
        sim_vol = float(risk_cfg.get("backtest_sim_volume_lots", 1.0))
        tex_dir = "LONG" if str(direction).upper() in ("LONG", "BUY") else "SHORT"

        if ql_emitter:
            desk_extra = {
                "engine": STRATEGY_ID,
                "hypothesis": HYPOTHESIS_ID,
                "sweep_id": sig.get("sweep_id"),
                "setup_bar_index": int(sig.get("setup_bar", -1)),
                "entry_price_market": entry_price,
            }
            se_payload = build_signal_evaluated_payload(
                decision_cycle_id=decision_cycle_id,
                session=current_session,
                regime=regime_str,
                signal_type="hyp_002_reclaim_entry",
                signal_direction=direction,
                confidence=1.0,
                system_mode=system_mode,
                bypassed_by_mode=list(bypassed_by_mode),
                setup_type=STRATEGY_ID,
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
                strategy_id=STRATEGY_ID,
                symbol=symbol,
                decision_cycle_id=decision_cycle_id,
                payload={
                    "signal_id": signal_id,
                    "type": "hyp_002_reclaim_entry",
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
                strategy_id=STRATEGY_ID,
                symbol=symbol,
                decision_cycle_id=decision_cycle_id,
                payload=se_payload,
            )
            ql_emitter.emit(
                event_type="risk_guard_decision",
                trace_id=trace_id,
                timestamp_utc=ts_iso,
                account_id=account_id,
                strategy_id=STRATEGY_ID,
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
                strategy_id=STRATEGY_ID,
                symbol=symbol,
                decision_cycle_id=decision_cycle_id,
                payload={
                    "decision": "ENTER",
                    "reason": STRATEGY_ID,
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
                strategy_id=STRATEGY_ID,
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
                strategy_id=STRATEGY_ID,
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
                strategy_id=STRATEGY_ID,
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
                    "hypothesis": HYPOTHESIS_ID,
                    "sweep_id": sig.get("sweep_id"),
                },
            )
            exit_ts_iso = _bar_timestamp_utc_iso(result["exit_ts"])
            ql_emitter.emit(
                event_type="trade_closed",
                trace_id=trace_id,
                timestamp_utc=exit_ts_iso,
                account_id=account_id,
                strategy_id=STRATEGY_ID,
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
                    "hypothesis": HYPOTHESIS_ID,
                    "sweep_id": sig.get("sweep_id"),
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
        "%s %s HYP-002: %d trades | max %d fills per UTC day",
        symbol,
        tf,
        len(trades),
        max_per_day,
    )

    metrics_out: Optional[Dict[str, Any]] = None
    if trades:
        from src.quantbuild.backtest.metrics import compute_metrics

        m = compute_metrics(trades)
        metrics_out = dict(m)
        logger.info(
            "HYP-002 result: net_pnl=%.2f pf=%.2f wr=%.1f%% dd=%.2fR n=%d",
            m.get("net_pnl", 0),
            m.get("profit_factor", 0),
            m.get("win_rate", 0),
            m.get("max_drawdown", 0),
            m.get("trade_count", 0),
        )

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
