"""Tests for merged config snapshot (strategy-effective parameters)."""

from __future__ import annotations

from pathlib import Path

import yaml

from src.quantbuild.config_runtime_snapshot import (
    REDACTED,
    runtime_config_for_artifact,
    write_runtime_config_yaml,
)


def test_strips_internal_quantbuild_keys():
    cfg = {"symbol": "XAUUSD", "_quantbuild_config_path": "/x/y.yaml", "risk": {"max_daily_loss_r": 2.0}}
    out = runtime_config_for_artifact(cfg)
    assert "_quantbuild_config_path" not in out
    assert out["symbol"] == "XAUUSD"
    assert out["risk"]["max_daily_loss_r"] == 2.0


def test_redacts_sensitive_key_substrings():
    cfg = {
        "news": {"newsapi_key": "secret123"},
        "broker": {"token": "t", "account_id": "123"},
        "nested": {"client_secret": "x"},
    }
    out = runtime_config_for_artifact(cfg)
    assert out["news"]["newsapi_key"] == REDACTED
    assert out["broker"]["token"] == REDACTED
    assert out["broker"]["account_id"] == "123"
    assert out["nested"]["client_secret"] == REDACTED


def test_write_round_trip(tmp_path: Path):
    cfg = {"backtest": {"tp_r": 2.5}, "ai": {"openai_api_key": "sk-xx"}}
    p = tmp_path / "out.yaml"
    write_runtime_config_yaml(cfg, p)
    loaded = yaml.safe_load(p.read_text(encoding="utf-8"))
    assert loaded["backtest"]["tp_r"] == 2.5
    assert loaded["ai"]["openai_api_key"] == REDACTED
    assert "openai_api_key" in loaded["ai"]
