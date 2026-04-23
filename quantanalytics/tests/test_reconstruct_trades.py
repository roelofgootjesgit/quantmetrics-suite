"""Smoke tests for trades_fact reconstruction."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from quantmetrics_analytics.ingestion.jsonl import load_events_from_paths
from quantmetrics_analytics.processing.normalize import events_to_dataframe
from quantmetrics_analytics.transforms.reconstruct_trades import reconstruct_trades

_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "sample_events.jsonl"


def test_fixture_has_no_fills_returns_empty_columns() -> None:
    events = load_events_from_paths([_FIXTURE])
    df = events_to_dataframe(events)
    out = reconstruct_trades(df)
    assert out.empty


def test_one_fill_joins_trade_executed_and_allow_reason() -> None:
    raw = [
        {
            "event_id": "1",
            "event_type": "risk_guard_decision",
            "event_version": 1,
            "timestamp_utc": "2025-06-01T10:00:00Z",
            "ingested_at_utc": "2025-06-01T10:00:00Z",
            "source_system": "quantbuild",
            "source_component": "backtest_engine",
            "environment": "dry_run",
            "run_id": "bt_run",
            "session_id": "sess",
            "source_seq": 1,
            "trace_id": "trace-a",
            "severity": "info",
            "payload": {"guard_name": "backtest_pipeline", "decision": "ALLOW", "reason": "simulated_execution"},
            "strategy_id": "sqe_backtest",
            "symbol": "XAUUSD",
        },
        {
            "event_id": "2",
            "event_type": "order_submitted",
            "event_version": 1,
            "timestamp_utc": "2025-06-01T10:00:01Z",
            "ingested_at_utc": "2025-06-01T10:00:01Z",
            "source_system": "quantbuild",
            "source_component": "backtest_engine",
            "environment": "dry_run",
            "run_id": "bt_run",
            "session_id": "sess",
            "source_seq": 2,
            "trace_id": "trace-a",
            "severity": "info",
            "payload": {"order_ref": "BT-a", "side": "LONG", "volume": 1.0},
            "order_ref": "BT-a",
            "strategy_id": "sqe_backtest",
            "symbol": "XAUUSD",
        },
        {
            "event_id": "3",
            "event_type": "order_filled",
            "event_version": 1,
            "timestamp_utc": "2025-06-01T10:00:02Z",
            "ingested_at_utc": "2025-06-01T10:00:02Z",
            "source_system": "quantbuild",
            "source_component": "backtest_engine",
            "environment": "dry_run",
            "run_id": "bt_run",
            "session_id": "sess",
            "source_seq": 3,
            "trace_id": "trace-a",
            "severity": "info",
            "payload": {"order_ref": "BT-a", "fill_price": 2650.5},
            "order_ref": "BT-a",
            "strategy_id": "sqe_backtest",
            "symbol": "XAUUSD",
        },
        {
            "event_id": "4",
            "event_type": "trade_executed",
            "event_version": 1,
            "timestamp_utc": "2025-06-01T10:00:03Z",
            "ingested_at_utc": "2025-06-01T10:00:03Z",
            "source_system": "quantbuild",
            "source_component": "backtest_engine",
            "environment": "dry_run",
            "run_id": "bt_run",
            "session_id": "sess",
            "source_seq": 4,
            "trace_id": "trace-a",
            "severity": "info",
            "payload": {
                "signal_id": "sig",
                "direction": "LONG",
                "trade_id": "BT-a",
                "session": "London",
                "regime": "compression",
            },
            "order_ref": "BT-a",
            "strategy_id": "sqe_backtest",
            "symbol": "XAUUSD",
        },
    ]
    df = events_to_dataframe(raw)
    out = reconstruct_trades(df)
    assert len(out) == 1
    row = out.iloc[0]
    assert row["trade_id"] == "BT-a"
    assert row["entry_price"] == 2650.5
    assert row["side"] == "LONG"
    assert row["regime_at_entry"] == "compression"
    assert row["session_at_entry"] == "London"
    assert row["risk_decision_reason"] == "simulated_execution"
    assert row["qty"] == 1.0
    assert pd.isna(row["pnl_r"])


def test_trade_closed_attaches_pnl_when_present() -> None:
    raw = [
        {
            "event_id": "1",
            "event_type": "order_filled",
            "event_version": 1,
            "timestamp_utc": "2025-06-01T12:00:00Z",
            "ingested_at_utc": "2025-06-01T12:00:00Z",
            "source_system": "quantbuild",
            "source_component": "x",
            "environment": "dry_run",
            "run_id": "r",
            "session_id": "s",
            "source_seq": 1,
            "trace_id": "z1",
            "severity": "info",
            "payload": {"order_ref": "T1", "fill_price": 100.0},
            "symbol": "XAUUSD",
        },
        {
            "event_id": "2",
            "event_type": "trade_closed",
            "event_version": 1,
            "timestamp_utc": "2025-06-01T15:00:00Z",
            "ingested_at_utc": "2025-06-01T15:00:00Z",
            "source_system": "quantbuild",
            "source_component": "x",
            "environment": "dry_run",
            "run_id": "r",
            "session_id": "s",
            "source_seq": 2,
            "trace_id": "z1",
            "severity": "info",
            "payload": {"pnl_r": 1.25, "pnl_abs": 50.0, "exit_price": 101.0, "exit": "TP"},
            "symbol": "XAUUSD",
        },
    ]
    df = events_to_dataframe(raw)
    out = reconstruct_trades(df)
    assert len(out) == 1
    assert out.iloc[0]["pnl_r"] == 1.25
    assert out.iloc[0]["pnl_abs"] == 50.0
    assert out.iloc[0]["exit_price"] == 101.0
    assert out.iloc[0]["holding_time_sec"] == 3 * 3600.0
    assert out.iloc[0]["exit"] == "TP"
