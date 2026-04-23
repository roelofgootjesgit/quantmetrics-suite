"""Tests for the correlation-aware portfolio heat engine + cluster risk."""
import pytest

from src.quantbuild.execution.portfolio_heat import (
    PortfolioHeatEngine,
    ClusterRiskEngine,
    _get_correlation,
)


@pytest.fixture
def engine():
    return PortfolioHeatEngine({
        "max_portfolio_heat_pct": 6.0,
        "max_instrument_heat_pct": 3.0,
        "max_correlated_exposure": 2,
        "max_same_direction": 4,
    })


def test_empty_engine(engine):
    assert engine.naive_heat == 0.0
    assert engine.effective_heat == 0.0
    assert engine.open_positions == []


def test_single_position(engine):
    engine.add_position("XAUUSD", "LONG", 1.5, "metals")
    assert engine.naive_heat == 1.5
    assert engine.effective_heat == 1.5
    assert len(engine.open_positions) == 1


def test_uncorrelated_positions_reduce_effective_heat(engine):
    engine.add_position("XAUUSD", "LONG", 1.5, "metals")
    engine.add_position("USDJPY", "LONG", 1.5, "fx_major")
    # Near-zero correlation -> effective heat < naive heat
    assert engine.naive_heat == 3.0
    assert engine.effective_heat < engine.naive_heat


def test_instrument_heat(engine):
    engine.add_position("XAUUSD", "LONG", 1.5, "metals")
    engine.add_position("XAUUSD", "SHORT", 1.0, "metals")
    assert engine.instrument_heat("XAUUSD") == 2.5
    assert engine.instrument_heat("GBPUSD") == 0.0


def test_can_open_respects_max_heat(engine):
    # Fill up to near limit — same instrument to avoid diversification benefit
    engine.add_position("XAUUSD", "LONG", 2.9, "metals")
    engine.add_position("XAUUSD", "LONG", 2.9, "metals")
    ok, reason = engine.can_open("XAUUSD", "LONG", 1.0, "metals")
    assert not ok


def test_can_open_respects_instrument_limit(engine):
    engine.add_position("XAUUSD", "LONG", 2.5, "metals")
    ok, reason = engine.can_open("XAUUSD", "SHORT", 1.0, "metals")
    assert not ok
    assert "instrument_heat" in reason


def test_remove_position(engine):
    engine.add_position("XAUUSD", "LONG", 1.5, "metals")
    assert engine.naive_heat == 1.5
    removed = engine.remove_position("XAUUSD")
    assert removed is True
    assert engine.naive_heat == 0.0


def test_clear(engine):
    engine.add_position("XAUUSD", "LONG", 1.5, "metals")
    engine.add_position("GBPUSD", "SHORT", 1.0, "fx_major")
    engine.clear()
    assert engine.naive_heat == 0.0
    assert len(engine.open_positions) == 0


def test_get_status(engine):
    engine.add_position("XAUUSD", "LONG", 1.5, "metals")
    status = engine.get_status()
    assert status["positions"] == 1
    assert status["naive_heat"] == 1.5
    assert "XAUUSD" in status["per_instrument"]


def test_correlation_lookup():
    assert _get_correlation("XAUUSD", "XAUUSD") == 1.0
    assert _get_correlation("XAUUSD", "GBPUSD") == _get_correlation("GBPUSD", "XAUUSD")
    assert abs(_get_correlation("XAUUSD", "GBPUSD")) < 0.1


def test_get_status_includes_clusters(engine):
    status = engine.get_status()
    assert "clusters" in status


# ── Cluster Risk Engine Tests ─────────────────────────────────────────

@pytest.fixture
def cluster_engine():
    return ClusterRiskEngine({})


def test_cluster_gbp_nzd_blocks_third(engine):
    """GBP+NZD cluster: max 2 concurrent, blocks third entry."""
    engine.add_position("GBPUSD", "LONG", 0.5)
    engine.add_position("NZDUSD", "LONG", 0.5)
    ok, reason = engine.can_open("GBPUSD", "SHORT", 0.5)
    assert not ok
    assert "cluster" in reason.lower()


def test_cluster_chf_eur_blocks_second(engine):
    """CHF+EUR inverse cluster: max 1 concurrent."""
    engine.add_position("USDCHF", "LONG", 0.5)
    ok, reason = engine.can_open("EURUSD", "SHORT", 0.5)
    assert not ok
    assert "cluster" in reason.lower()


def test_cluster_allows_within_limit(engine):
    """One position in cluster is fine."""
    engine.add_position("GBPUSD", "LONG", 0.5)
    ok, reason = engine.can_open("NZDUSD", "LONG", 0.5)
    assert ok


def test_unclustered_instrument_not_blocked(engine):
    """XAU is not in any FX cluster, should not be blocked by cluster rules."""
    engine.add_position("GBPUSD", "LONG", 0.5)
    engine.add_position("NZDUSD", "LONG", 0.5)
    ok, reason = engine.can_open("XAUUSD", "LONG", 0.5)
    assert ok


def test_cluster_sizing_penalty(cluster_engine):
    """When GBP is open, NZD gets sizing penalty."""
    from src.quantbuild.execution.portfolio_heat import OpenPosition
    positions = [OpenPosition("GBPUSD", "LONG", 0.5)]
    mult = cluster_engine.get_sizing_multiplier("NZDUSD", positions)
    assert mult < 1.0
    assert mult == 0.7  # risk_on_fx penalty


def test_cluster_sizing_no_penalty_when_no_peer(cluster_engine):
    from src.quantbuild.execution.portfolio_heat import OpenPosition
    positions = [OpenPosition("XAUUSD", "LONG", 1.0)]
    mult = cluster_engine.get_sizing_multiplier("NZDUSD", positions)
    assert mult == 1.0


def test_cluster_adjusted_risk(engine):
    """Engine applies cluster penalty through get_cluster_adjusted_risk."""
    engine.add_position("GBPUSD", "LONG", 0.5)
    adjusted = engine.get_cluster_adjusted_risk("NZDUSD", 1.0)
    assert adjusted == pytest.approx(0.7, abs=0.01)


def test_priority_resolution(cluster_engine):
    assert cluster_engine.resolve_priority("XAUUSD", "NZDUSD") == "XAUUSD"
    assert cluster_engine.resolve_priority("GBPUSD", "USDCHF") == "GBPUSD"
    assert cluster_engine.resolve_priority("USDJPY", "NZDUSD") == "NZDUSD"


def test_cluster_status(engine):
    engine.add_position("GBPUSD", "LONG", 0.5)
    status = engine.get_status()
    clusters = status["clusters"]
    assert "risk_on_fx" in clusters
    assert clusters["risk_on_fx"]["active"] == 1
