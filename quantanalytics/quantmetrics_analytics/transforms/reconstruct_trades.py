"""Silver layer: canonical trade-level facts from normalized QuantLog events.

Input is a DataFrame from ``events_to_dataframe`` (see ``processing.normalize``):
envelope columns + ``payload_*`` flattened keys.

One row per ``order_filled`` (entry fill). When a matching ``trade_closed`` or
``position_closed`` exists on the same ``trace_id`` at or after entry fill time,
``pnl_r``, ``holding_time_sec``, ``exit`` (simulator tag), and prices are filled
from the close payload (live feeds may omit some fields).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

import pandas as pd


TRADES_FACT_COLUMNS: tuple[str, ...] = (
    "trade_id",
    "trace_id",
    "run_id",
    "strategy_id",
    "symbol",
    "side",
    "qty",
    "entry_time",
    "entry_price",
    "exit_time",
    "exit_price",
    "exit",
    "pnl_abs",
    "pnl_r",
    "mae",
    "mfe",
    "holding_time_sec",
    "regime_at_entry",
    "session_at_entry",
    "risk_decision_reason",
)


def _empty_trades_fact() -> pd.DataFrame:
    return pd.DataFrame(columns=list(TRADES_FACT_COLUMNS))


def _pick(row: pd.Series, *names: str) -> Any:
    for n in names:
        if n in row.index and pd.notna(row[n]) and row[n] != "":
            return row[n]
    return pd.NA


def _to_float(val: Any) -> Optional[float]:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _parse_ts(series_or_val: Any) -> Optional[pd.Timestamp]:
    if series_or_val is None or (isinstance(series_or_val, float) and pd.isna(series_or_val)):
        return None
    ts = pd.Timestamp(series_or_val)
    if ts.tzinfo is None:
        ts = ts.tz_localize("UTC")
    else:
        ts = ts.tz_convert("UTC")
    return ts


@dataclass
class TradeRecord:
    """Canonical trade row (mirror of ``trades_fact`` schema)."""

    trade_id: str
    trace_id: str
    run_id: str
    strategy_id: Optional[str]
    symbol: Optional[str]
    side: Optional[str]
    qty: Optional[float]
    entry_time: Optional[pd.Timestamp]
    entry_price: Optional[float]
    exit_time: Optional[pd.Timestamp]
    exit_price: Optional[float]
    exit: Optional[str]
    pnl_abs: Optional[float]
    pnl_r: Optional[float]
    mae: Optional[float]
    mfe: Optional[float]
    holding_time_sec: Optional[float]
    regime_at_entry: Optional[str]
    session_at_entry: Optional[str]
    risk_decision_reason: Optional[str]


def reconstruct_trades(events: pd.DataFrame) -> pd.DataFrame:
    """
    Build ``trades_fact``-style rows from normalized QuantLog events.

    - One row per ``order_filled`` (treated as entry fill).
    - Exit/PnL: first ``trade_closed`` or ``position_closed`` on the same
      ``trace_id`` at or after entry time (if present).
    - Context (side, regime, session): prefers ``trade_executed`` on the same
      ``trace_id``, then ``trade_action`` ENTER, then ``signal_evaluated``.
    - ``risk_decision_reason``: last ``risk_guard_decision`` with
      ``payload_decision == ALLOW`` before or at fill time for that trace.

    When close events are missing, exit/PnL/holding columns remain NA.
    """
    if events.empty or "event_type" not in events.columns:
        return _empty_trades_fact()

    df = events.copy()
    if "timestamp_utc" in df.columns:
        df["_ts"] = pd.to_datetime(df["timestamp_utc"], utc=True, errors="coerce")
    else:
        df["_ts"] = pd.NaT

    fills_idx = df["event_type"] == "order_filled"
    fills = df[fills_idx].sort_values("_ts")
    if fills.empty:
        return _empty_trades_fact()

    close_mask = df["event_type"].isin(("trade_closed", "position_closed"))
    closes = df[close_mask].sort_values("_ts")

    rg_mask = df["event_type"] == "risk_guard_decision"
    risk_rows = df[rg_mask].sort_values("_ts")

    exec_mask = df["event_type"] == "trade_executed"
    exec_by_trace = (
        df[exec_mask].sort_values("_ts").drop_duplicates("trace_id", keep="last").set_index("trace_id")
    )

    ta_enter = df[
        (df["event_type"] == "trade_action") & (df.get("payload_decision") == "ENTER")
    ].sort_values("_ts").drop_duplicates("trace_id", keep="last")

    sig_ev = df[df["event_type"] == "signal_evaluated"].sort_values("_ts").drop_duplicates(
        "trace_id", keep="last"
    )

    vol_mask = df["event_type"] == "order_submitted"
    vol_by_trace = {}
    for tid, g in df[vol_mask].groupby("trace_id"):
        last = g.sort_values("_ts").iloc[-1]
        v = _pick(last, "payload_volume", "payload_qty")
        vol_by_trace[tid] = _to_float(v)

    records: list[dict[str, Any]] = []

    for _, fill in fills.iterrows():
        trace_id = fill.get("trace_id")
        if trace_id is None or (isinstance(trace_id, float) and pd.isna(trace_id)):
            continue

        fill_ts = fill["_ts"]
        tid = str(trace_id)

        close_row = None
        if not closes.empty and pd.notna(fill_ts):
            after = closes[(closes["trace_id"].astype(str) == tid) & (closes["_ts"] >= fill_ts)]
            if not after.empty:
                close_row = after.iloc[0]

        ex = exec_by_trace.loc[tid] if tid in exec_by_trace.index else None

        side = None
        if ex is not None:
            side = _pick(ex, "payload_direction")
        if (side is None or pd.isna(side)) and not ta_enter.empty:
            ta_m = ta_enter[ta_enter["trace_id"].astype(str) == tid]
            if not ta_m.empty:
                side = _pick(ta_m.iloc[-1], "payload_side")

        regime = None
        session = None
        if ex is not None:
            regime = _pick(ex, "payload_regime")
            session = _pick(ex, "payload_session")
        if (regime is None or pd.isna(regime) or session is None or pd.isna(session)) and not sig_ev.empty:
            sg = sig_ev[sig_ev["trace_id"].astype(str) == tid]
            if not sg.empty:
                row_s = sg.iloc[-1]
                if regime is None or pd.isna(regime):
                    regime = _pick(row_s, "payload_regime")
                if session is None or pd.isna(session):
                    session = _pick(row_s, "payload_session")

        risk_reason = pd.NA
        if not risk_rows.empty and pd.notna(fill_ts):
            cand = risk_rows[risk_rows["trace_id"].astype(str) == tid]
            cand = cand[cand["_ts"] <= fill_ts]
            allow = cand.iloc[0:0]
            if not cand.empty and "payload_decision" in cand.columns:
                allow = cand[cand["payload_decision"] == "ALLOW"]
            if not allow.empty:
                last_r = allow.iloc[-1]
                risk_reason = _pick(last_r, "payload_reason")

        trade_id_val = pd.NA
        if ex is not None:
            trade_id_val = _pick(ex, "payload_trade_id")
        if trade_id_val is None or pd.isna(trade_id_val):
            trade_id_val = _pick(fill, "payload_order_ref", "order_ref")
        if trade_id_val is None or pd.isna(trade_id_val):
            trade_id_val = tid

        entry_price = _to_float(_pick(fill, "payload_fill_price", "payload_price"))

        exit_time = pd.NaT
        exit_price = pd.NA
        exit_tag = pd.NA
        pnl_abs = pd.NA
        pnl_r = pd.NA
        mae = pd.NA
        mfe = pd.NA
        if close_row is not None:
            exit_time = close_row["_ts"]
            exit_price = _pick(close_row, "payload_exit_price", "payload_price", "payload_fill_price")
            exit_price = pd.NA if exit_price is pd.NA else _to_float(exit_price)
            exit_tag = _pick(close_row, "payload_exit", "payload_exit_reason", "payload_exit_tag")
            pnl_abs = _pick(close_row, "payload_pnl_abs", "payload_pnl", "payload_net_pnl")
            pnl_abs = pd.NA if pnl_abs is pd.NA else _to_float(pnl_abs)
            pnl_r = _pick(close_row, "payload_pnl_r", "payload_r_multiple", "payload_r")
            pnl_r = pd.NA if pnl_r is pd.NA else _to_float(pnl_r)
            mae = _pick(close_row, "payload_mae", "payload_mae_r")
            mae = pd.NA if mae is pd.NA else _to_float(mae)
            mfe = _pick(close_row, "payload_mfe", "payload_mfe_r")
            mfe = pd.NA if mfe is pd.NA else _to_float(mfe)

        qty = vol_by_trace.get(tid)
        qty = qty if qty is not None else _to_float(_pick(fill, "payload_volume", "payload_qty"))

        entry_ts = fill_ts if pd.notna(fill_ts) else pd.NaT
        hold_sec = pd.NA
        if pd.notna(entry_ts) and pd.notna(exit_time):
            hold_sec = float((exit_time - entry_ts).total_seconds())

        records.append(
            {
                "trade_id": str(trade_id_val),
                "trace_id": tid,
                "run_id": str(fill.get("run_id", ""))
                if fill.get("run_id") is not None and not pd.isna(fill.get("run_id"))
                else pd.NA,
                "strategy_id": _pick(fill, "strategy_id"),
                "symbol": _pick(fill, "symbol", "payload_symbol"),
                "side": side if side is not None and not pd.isna(side) else pd.NA,
                "qty": qty if qty is not None else pd.NA,
                "entry_time": entry_ts,
                "entry_price": entry_price if entry_price is not None else pd.NA,
                "exit_time": exit_time,
                "exit_price": exit_price if exit_price is not None else pd.NA,
                "exit": exit_tag if exit_tag is not None and not pd.isna(exit_tag) else pd.NA,
                "pnl_abs": pnl_abs,
                "pnl_r": pnl_r,
                "mae": mae,
                "mfe": mfe,
                "holding_time_sec": hold_sec,
                "regime_at_entry": regime if regime is not None and not pd.isna(regime) else pd.NA,
                "session_at_entry": session if session is not None and not pd.isna(session) else pd.NA,
                "risk_decision_reason": risk_reason,
            }
        )

    out = pd.DataFrame.from_records(records)
    if out.empty:
        return _empty_trades_fact()

    for c in TRADES_FACT_COLUMNS:
        if c not in out.columns:
            out[c] = pd.NA

    out = out.reindex(columns=list(TRADES_FACT_COLUMNS))
    return out
