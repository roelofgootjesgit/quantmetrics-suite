"""Tests for central system_mode filter resolution."""
import pytest

from src.quantbuild.policy.system_mode import (
    FILTER_KEYS,
    SYSTEM_MODE_EDGE_DISCOVERY,
    SYSTEM_MODE_PRODUCTION,
    bypassed_filters_vs_production,
    normalize_system_mode,
    resolve_effective_filters,
)


def test_normalize_aliases():
    assert normalize_system_mode(None) == SYSTEM_MODE_PRODUCTION
    assert normalize_system_mode("edge") == SYSTEM_MODE_EDGE_DISCOVERY
    assert normalize_system_mode("EDGE_DISCOVERY") == SYSTEM_MODE_EDGE_DISCOVERY
    assert normalize_system_mode("production") == SYSTEM_MODE_PRODUCTION


def test_resolve_production_defaults():
    mode, eff = resolve_effective_filters({"system_mode": "PRODUCTION"})
    assert mode == SYSTEM_MODE_PRODUCTION
    assert eff["regime"] is True
    assert eff["research_raw_first"] is False
    assert set(eff) == set(FILTER_KEYS)


def test_bypassed_vs_production_edge_discovery():
    _, eff = resolve_effective_filters({"system_mode": "EDGE_DISCOVERY"})
    bypass = bypassed_filters_vs_production(eff)
    assert "regime" in bypass
    assert "session" in bypass
    assert "daily_loss" not in bypass


def test_resolve_edge_defaults():
    mode, eff = resolve_effective_filters({"system_mode": "EDGE_DISCOVERY"})
    assert mode == SYSTEM_MODE_EDGE_DISCOVERY
    assert eff["structure_h1_gate"] is False
    assert eff["regime"] is False
    assert eff["session"] is False
    assert eff["cooldown"] is False
    assert eff["news"] is False
    assert eff["position_limit"] is False
    assert eff["daily_loss"] is True
    assert eff["spread"] is True
    assert eff["research_raw_first"] is True


def test_user_filters_override_mode():
    _, eff = resolve_effective_filters(
        {"system_mode": "EDGE_DISCOVERY", "filters": {"regime": True}}
    )
    assert eff["regime"] is True
    assert eff["session"] is False


def test_unknown_mode_warns():
    with pytest.warns(UserWarning, match="Unknown system_mode"):
        assert normalize_system_mode("typo_mode") == SYSTEM_MODE_PRODUCTION
