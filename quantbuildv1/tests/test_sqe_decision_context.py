"""SQE decision_context for QuantLog must stay JSON-serializable."""

from __future__ import annotations

import json

import pandas as pd

from src.quantbuild.strategies.sqe_xauusd import (
    get_sqe_default_config,
    _compute_modules_once,
    sqe_decision_context_at_bar,
)


def test_sqe_decision_context_json_serializable() -> None:
    idx = pd.date_range("2024-01-01", periods=60, freq="15min", tz="UTC")
    rng = pd.Series(range(60), dtype=float)
    data = pd.DataFrame(
        {
            "open": 2000 + rng,
            "high": 2001 + rng,
            "low": 1999 + rng,
            "close": 2000 + rng,
        },
        index=idx,
    )
    cfg = get_sqe_default_config()
    df = _compute_modules_once(data, cfg)
    ctx = sqe_decision_context_at_bar(df, "LONG", len(df) - 1, cfg)
    json.dumps(ctx)
    assert ctx["decision_context_version"] == 1
    assert ctx["strategy"] == "sqe_xauusd"
    assert "entry_signal" in ctx
    assert "fvg_quality" in ctx
    assert isinstance(ctx["fvg_quality"], (int, float))
    assert 0.0 <= float(ctx["fvg_quality"]) <= 1.0


def test_sqe_decision_context_bad_index() -> None:
    idx = pd.date_range("2024-01-01", periods=5, freq="15min", tz="UTC")
    data = pd.DataFrame(
        {"open": 1.0, "high": 2.0, "low": 0.5, "close": 1.5},
        index=idx,
    )
    df = _compute_modules_once(data, get_sqe_default_config())
    ctx = sqe_decision_context_at_bar(df, "LONG", 9999, get_sqe_default_config())
    assert ctx.get("error") == "bar_index_out_of_range"
