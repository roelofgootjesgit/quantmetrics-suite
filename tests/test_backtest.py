"""Unit tests for backtest engine and metrics."""
import json
import numpy as np
import pandas as pd
import pytest
from datetime import datetime, timedelta

from src.quantbuild.models.trade import Trade, calculate_rr
from src.quantbuild.backtest.metrics import compute_metrics, compute_metrics_by_direction, compute_full_report
from src.quantbuild.backtest.engine import _simulate_trade, _prepare_sim_cache, run_backtest


def _make_ohlcv(n=200, base=2000.0, seed=42):
    rng = np.random.RandomState(seed)
    dates = pd.date_range("2025-01-01", periods=n, freq="15min", tz="UTC")
    close = base + np.cumsum(rng.randn(n) * 2)
    high = close + rng.uniform(0.5, 3.0, n)
    low = close - rng.uniform(0.5, 3.0, n)
    return pd.DataFrame({"open": close + rng.randn(n)*0.5, "high": high, "low": low, "close": close, "volume": rng.randint(100,1000,n)}, index=dates)


def _make_trades(n=10):
    trades = []
    base_time = datetime(2025, 1, 1, 10, 0)
    for i in range(n):
        is_win = i % 3 != 0
        trades.append(Trade(
            timestamp_open=base_time + timedelta(hours=i),
            timestamp_close=base_time + timedelta(hours=i, minutes=45),
            symbol="XAUUSD", direction="LONG" if i % 2 == 0 else "SHORT",
            entry_price=2000.0, exit_price=2004.0 if is_win else 1998.0,
            sl=1998.0, tp=2004.0,
            profit_usd=4.0 if is_win else -2.0, profit_r=2.0 if is_win else -1.0,
            result="WIN" if is_win else "LOSS", regime="TRENDING" if i < 5 else "RANGING",
        ))
    return trades


class TestMetrics:
    def test_empty(self):
        assert compute_metrics([])["trade_count"] == 0

    def test_basic(self):
        m = compute_metrics(_make_trades(10))
        assert m["trade_count"] == 10
        assert 0 <= m["win_rate"] <= 100

    def test_by_direction(self):
        by_dir = compute_metrics_by_direction(_make_trades(10))
        assert "LONG" in by_dir and "SHORT" in by_dir

    def test_full_report(self):
        report = compute_full_report(_make_trades(10))
        assert all(k in report for k in ["overall", "by_direction", "by_regime", "by_session"])


class TestSimulateTrade:
    def test_trade_produces_result(self):
        df = _make_ohlcv(200)
        cache = _prepare_sim_cache(df)
        result = _simulate_trade(df, 50, "LONG", 2.0, 1.0, _cache=cache)
        assert result["result"] in ("WIN", "LOSS", "TIMEOUT")
        assert result["entry_price"] > 0

    def test_cache_consistency(self):
        df = _make_ohlcv(200)
        cache = _prepare_sim_cache(df)
        r1 = _simulate_trade(df, 50, "LONG", 2.0, 1.0, _cache=cache)
        r2 = _simulate_trade(df, 50, "LONG", 2.0, 1.0, _cache=None)
        assert r1["result"] == r2["result"]
        assert r1["entry_price"] == pytest.approx(r2["entry_price"])


class TestBacktestQuantLog:
    """Backtest emits QuantLog JSONL when ``quantlog.enabled`` (same contract as live_runner)."""

    def test_writes_events_when_quantlog_enabled(self, tmp_path, monkeypatch):
        import src.quantbuild.backtest.engine as eng

        df = _make_ohlcv(320)
        precomputed = pd.Series("trend", index=df.index)

        def fake_load_parquet(base_path, symbol, timeframe, start=None, end=None):
            if timeframe == "15m":
                return df
            return pd.DataFrame()

        def fake_run_sqe(data, direction, sqe_cfg, _precomputed_df=None):
            out = pd.Series(False, index=data.index)
            if direction == "LONG":
                out.iloc[150] = True
            return out

        monkeypatch.setattr(eng, "load_parquet", fake_load_parquet)
        monkeypatch.setattr(eng, "ensure_data", lambda **kwargs: df)
        monkeypatch.setattr(eng, "run_sqe_conditions", fake_run_sqe)

        ql_dir = tmp_path / "quantlog_bt"
        cfg = {
            "symbol": "XAUUSD",
            "timeframes": ["15m"],
            "data": {"base_path": str(tmp_path / "data")},
            "backtest": {"default_period_days": 365, "tp_r": 2.0, "sl_r": 1.0, "session_mode": "extended"},
            "risk": {"max_daily_loss_r": 99.0, "equity_kill_switch_pct": 99.0},
            "strategy": {},
            "quantlog": {
                "enabled": True,
                "base_path": str(ql_dir),
                "environment": "backtest",
                "run_id": "bt_test_run",
                "session_id": "bt_test_session",
                "consolidated_run_file": True,
            },
            "news": {"enabled": False},
        }

        trades = run_backtest(cfg, precomputed_regime=precomputed)
        assert len(trades) >= 1

        jsonl_path = ql_dir / "runs" / "bt_test_run.jsonl"
        assert jsonl_path.is_file(), f"missing consolidated {jsonl_path}"
        lines = jsonl_path.read_text(encoding="utf-8").strip().splitlines()
        assert lines, "empty quantbuild jsonl"

        parsed = [json.loads(line) for line in lines]
        types = [e["event_type"] for e in parsed]
        assert "signal_evaluated" in types
        assert "signal_detected" in types
        assert "trade_action" in types
        assert "risk_guard_decision" in types
        for e in parsed:
            if e["event_type"] in (
                "signal_detected",
                "signal_evaluated",
                "risk_guard_decision",
                "trade_action",
            ):
                assert e.get("decision_cycle_id"), f"missing decision_cycle_id on {e['event_type']}"
            if e["event_type"] == "signal_evaluated":
                pl = e["payload"]
                for k in ("session", "setup_type", "regime", "decision_cycle_id"):
                    assert str(pl.get(k) or "").strip(), f"signal_evaluated payload missing {k}"
        assert "order_submitted" in types
        assert "order_filled" in types
        assert "trade_executed" in types
        assert "trade_closed" in types

        closed_ev = next(e for e in (json.loads(line) for line in lines) if e["event_type"] == "trade_closed")
        assert closed_ev["payload"].get("pnl_r") is not None
        assert closed_ev["payload"].get("exit_price") is not None
        assert closed_ev["payload"].get("exit") in ("SL", "TP", "TIMEOUT")

        trade_ev = next(e for e in (json.loads(line) for line in lines) if e["event_type"] == "trade_executed")
        assert trade_ev["payload"].get("signal_id", "").startswith("sig_bt_")
        enter_ev = next(
            e
            for e in (json.loads(line) for line in lines)
            if e["event_type"] == "trade_action" and e["payload"].get("decision") == "ENTER"
        )
        assert enter_ev["payload"].get("trade_id")
        sf = [e for e in parsed if e["event_type"] == "signal_filtered"]
        if sf:
            assert all(e.get("decision_cycle_id") for e in sf), "signal_filtered should carry decision_cycle_id"


class TestSystemModeBacktest:
    """PRODUCTION vs EDGE_DISCOVERY: same candidate, regime skip blocks only in production."""

    def test_edge_discovery_bypasses_regime_skip(self, monkeypatch, tmp_path):
        import src.quantbuild.backtest.engine as eng

        df = _make_ohlcv(320)
        precomputed = pd.Series("expansion", index=df.index)

        def fake_load_parquet(base_path, symbol, timeframe, start=None, end=None):
            if timeframe == "15m":
                return df
            return pd.DataFrame()

        def fake_run_sqe(data, direction, sqe_cfg, _precomputed_df=None):
            out = pd.Series(False, index=data.index)
            if direction == "LONG":
                out.iloc[150] = True
            return out

        monkeypatch.setattr(eng, "load_parquet", fake_load_parquet)
        monkeypatch.setattr(eng, "ensure_data", lambda **kwargs: df)
        monkeypatch.setattr(eng, "run_sqe_conditions", fake_run_sqe)

        base_cfg = {
            "symbol": "XAUUSD",
            "timeframes": ["15m"],
            "data": {"base_path": str(tmp_path / "data")},
            "backtest": {"default_period_days": 365, "tp_r": 2.0, "sl_r": 1.0, "session_mode": "extended"},
            "risk": {"max_daily_loss_r": 99.0, "equity_kill_switch_pct": 99.0},
            "strategy": {},
            "quantlog": {"enabled": False},
            "news": {"enabled": False},
            "regime_profiles": {"expansion": {"skip": True}},
        }

        trades_prod = eng.run_backtest({**base_cfg, "system_mode": "PRODUCTION"}, precomputed_regime=precomputed)
        assert len(trades_prod) == 0

        trades_edge = eng.run_backtest({**base_cfg, "system_mode": "EDGE_DISCOVERY"}, precomputed_regime=precomputed)
        assert len(trades_edge) >= 1
