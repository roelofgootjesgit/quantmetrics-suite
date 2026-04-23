"""Tests for the adaptive mode layer."""
import pytest

from src.quantbuild.execution.adaptive_mode import AdaptiveModeLayer


@pytest.fixture
def layer():
    return AdaptiveModeLayer({
        "adaptive_mode": {
            "aggressive_dd_max": 1.0,
            "aggressive_momentum_window": 3,
            "defensive_dd": 3.0,
            "lockdown_dd": 5.0,
            "defensive_losing_streak": 3,
            "lockdown_losing_streak": 5,
            "recovery_wins": 2,
        }
    })


def test_initial_state(layer):
    assert layer.current_mode == "BASE"
    assert layer.risk_multiplier == 1.0


def test_stays_base_on_mixed_activity(layer):
    layer.record_trade(1.5)
    layer.record_trade(-1.0)
    layer.record_trade(-0.5)
    layer.record_trade(0.5)
    # Mixed results = not enough momentum for AGGRESSIVE, not enough losses for DEFENSIVE
    assert layer.current_mode == "BASE"


def test_defensive_on_losing_streak(layer):
    for _ in range(3):
        layer.record_trade(-1.0)
    assert layer.current_mode == "DEFENSIVE"
    assert layer.risk_multiplier < 1.0


def test_lockdown_on_severe_losses(layer):
    for _ in range(5):
        layer.record_trade(-1.0)
    assert layer.current_mode == "LOCKDOWN"
    assert layer.risk_multiplier <= 0.3


def test_defensive_on_drawdown(layer):
    layer.update_equity(5.0)  # peak at 5%
    layer.update_equity(1.5)  # DD = 3.5%
    assert layer.current_mode == "DEFENSIVE"


def test_lockdown_on_severe_drawdown(layer):
    layer.update_equity(8.0)
    layer.update_equity(2.5)  # DD = 5.5%
    assert layer.current_mode == "LOCKDOWN"


def test_recovery_from_defensive(layer):
    for _ in range(3):
        layer.record_trade(-1.0)
    assert layer.current_mode == "DEFENSIVE"
    # Win enough to recover
    layer.record_trade(1.5)
    layer.record_trade(1.5)
    assert layer.current_mode == "BASE"


def test_aggressive_with_momentum(layer):
    layer.update_equity(0.5)  # small DD from peak
    # Build momentum
    for _ in range(3):
        layer.record_trade(1.0)
    assert layer.current_mode == "AGGRESSIVE"
    assert layer.risk_multiplier > 1.0


def test_effective_risk_scaling(layer):
    base = 1.5
    # BASE mode
    assert layer.get_effective_risk(base) == base
    # Force AGGRESSIVE
    layer.update_equity(0.5)
    for _ in range(3):
        layer.record_trade(1.0)
    assert layer.get_effective_risk(base) > base


def test_effective_heat_scaling(layer):
    base_heat = 6.0
    assert layer.get_effective_heat_limit(base_heat) == base_heat
    # Force DEFENSIVE
    for _ in range(3):
        layer.record_trade(-1.0)
    assert layer.get_effective_heat_limit(base_heat) < base_heat


def test_get_status(layer):
    layer.record_trade(1.0)
    status = layer.get_status()
    assert "mode" in status
    assert "risk_multiplier" in status
    assert "consecutive_wins" in status
