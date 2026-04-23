"""Tests for AccountLifecycleManager — CHALLENGE -> FUNDED transitions."""
import pytest
from src.quantbuild.execution.account_lifecycle import (
    AccountLifecycleManager,
    AccountType,
    AccountStatus,
)


CHALLENGE_CFG = {
    "mode": "challenge",
    "instruments": {
        "XAUUSD": {"enabled": True, "engine": "sqe_trend"},
        "NAS100": {"enabled": True, "engine": "sqe_trend", "book": "throughput"},
        "EURUSD": {"enabled": False},
    },
    "risk": {"risk_per_trade_pct": 0.75},
    "kill_switches": {
        "max_total_dd_pct": 10.0,
        "challenge_reset_dd_pct": 8.0,
        "max_daily_loss_pct": 2.5,
    },
}

FUNDED_CFG = {
    "mode": "funded",
    "instruments": {
        "XAUUSD": {"enabled": True, "engine": "sqe_trend"},
        "EURUSD": {"enabled": True, "engine": "mean_reversion"},
        "NAS100": {"enabled": False},
    },
    "risk": {"risk_per_trade_pct": 0.5},
    "kill_switches": {
        "max_total_dd_pct": 5.0,
        "max_daily_loss_pct": 2.0,
        "consecutive_losing_days_halt": 3,
    },
}


@pytest.fixture
def mgr():
    return AccountLifecycleManager(CHALLENGE_CFG, FUNDED_CFG)


def test_create_challenge_account(mgr):
    state = mgr.create_account("ftmo-001", AccountType.CHALLENGE, 100_000)
    assert state.account_type == AccountType.CHALLENGE
    assert state.status == AccountStatus.ACTIVE
    assert state.current_equity == 100_000


def test_challenge_config_returns_nas100_enabled(mgr):
    mgr.create_account("ftmo-001", AccountType.CHALLENGE)
    instruments = mgr.get_enabled_instruments("ftmo-001")
    assert "XAUUSD" in instruments
    assert "NAS100" in instruments
    assert "EURUSD" not in instruments


def test_funded_config_returns_eurusd_enabled(mgr):
    mgr.create_account("funded-001", AccountType.FUNDED)
    instruments = mgr.get_enabled_instruments("funded-001")
    assert "XAUUSD" in instruments
    assert "EURUSD" in instruments
    assert "NAS100" not in instruments


def test_challenge_pass_triggers_funded_switch(mgr):
    mgr.create_account("ftmo-001", AccountType.CHALLENGE, 100_000)
    # Simulate reaching +10% target
    mgr.record_trade("ftmo-001", 10_500)  # push past 10%
    result = mgr.daily_check("ftmo-001")
    assert result["action"] == "SWITCH_TO_FUNDED"
    assert "new_account_id" in result


def test_challenge_fail_on_dd(mgr):
    mgr.create_account("ftmo-002", AccountType.CHALLENGE, 100_000)
    mgr.record_trade("ftmo-002", -8_500)  # push past 8% reset
    result = mgr.daily_check("ftmo-002")
    assert result["action"] == "FAILED"


def test_funded_halt_on_dd(mgr):
    mgr.create_account("funded-001", AccountType.FUNDED, 100_000)
    mgr.record_trade("funded-001", -5_100)  # past 5% DD
    result = mgr.daily_check("funded-001")
    assert result["action"] == "HALT"


def test_funded_daily_loss_halt(mgr):
    mgr.create_account("funded-002", AccountType.FUNDED, 100_000)
    mgr.record_trade("funded-002", -2_100)
    result = mgr.daily_check("funded-002")
    assert result["action"] == "HALT"
    assert "daily" in result.get("reason", "").lower()


def test_funded_consecutive_losing_days_risk_halved(mgr):
    mgr.create_account("funded-003", AccountType.FUNDED, 100_000)
    for _ in range(3):
        mgr.record_trade("funded-003", -100)
        mgr.start_new_day("funded-003")
    result = mgr.daily_check("funded-003")
    assert result.get("risk_override") == 0.5


def test_portfolio_summary(mgr):
    mgr.create_account("ch-1", AccountType.CHALLENGE, 100_000)
    mgr.create_account("fund-1", AccountType.FUNDED, 100_000)
    summary = mgr.get_portfolio_summary()
    assert summary["total_accounts"] == 2
    assert len(summary["active_challenges"]) == 1
    assert len(summary["active_funded"]) == 1


def test_payout_tracking(mgr):
    mgr.create_account("fund-1", AccountType.FUNDED, 100_000)
    mgr.record_payout("fund-1", 2500)
    mgr.record_payout("fund-1", 3000)
    state = mgr.accounts["fund-1"]
    assert state.payout_total == 5500
    assert state.months_funded == 2


def test_scaling_phase():
    assert AccountLifecycleManager._scaling_phase(0, 1) == "START"
    assert AccountLifecycleManager._scaling_phase(2, 1) == "PASS_1"
    assert AccountLifecycleManager._scaling_phase(4, 2) == "PASS_2"
    assert AccountLifecycleManager._scaling_phase(6, 3) == "SCALE"
