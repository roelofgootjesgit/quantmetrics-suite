"""Tests for PassAccelerator — phase-based challenge risk scaling."""
import pytest
from src.quantbuild.execution.pass_accelerator import PassAccelerator, PHASE_PROFILES


@pytest.fixture
def default_accel():
    cfg = {
        "pass_accelerator": {
            "target_pct": 10.0,
            "max_total_dd_pct": 10.0,
            "challenge_days": 30,
            "attack_until_day": 10,
            "secure_at_pct": 7.0,
            "coast_at_pct": 9.0,
            "dd_danger_zone_pct": 3.0,
        }
    }
    return PassAccelerator(cfg)


class TestPhaseTransitions:
    def test_starts_in_attack(self, default_accel):
        default_accel.start_challenge()
        assert default_accel.phase == "ATTACK"

    def test_attack_early_days(self, default_accel):
        default_accel.start_challenge()
        default_accel.update(equity_pct=2.0, day=5)
        assert default_accel.phase == "ATTACK"

    def test_normal_after_attack_period(self, default_accel):
        default_accel.start_challenge()
        default_accel.update(equity_pct=3.0, day=15)
        assert default_accel.phase == "NORMAL"

    def test_secure_near_target(self, default_accel):
        default_accel.start_challenge()
        default_accel.update(equity_pct=7.5, day=15)
        assert default_accel.phase == "SECURE"

    def test_coast_when_target_almost_reached(self, default_accel):
        default_accel.start_challenge()
        default_accel.update(equity_pct=9.5, day=15)
        assert default_accel.phase == "COAST"

    def test_secure_on_dd_danger(self, default_accel):
        """If DD is close to max, force SECURE regardless of timeline."""
        default_accel.start_challenge()
        default_accel.update(equity_pct=5.0, day=3)  # peak = 5
        default_accel.update(equity_pct=-2.0, day=4)  # DD = 7, danger = 10-3=7
        assert default_accel.phase == "SECURE"

    def test_attack_late_far_from_target(self, default_accel):
        """Late in challenge + far from target -> re-enter ATTACK."""
        default_accel.start_challenge()
        default_accel.update(equity_pct=3.0, day=22)
        assert default_accel.phase == "ATTACK"

    def test_funded_mode(self, default_accel):
        default_accel.start_challenge()
        default_accel.switch_to_funded()
        assert default_accel.phase == "FUNDED"
        default_accel.update(equity_pct=5.0, day=50)
        assert default_accel.phase == "FUNDED"


class TestRiskMultipliers:
    def test_attack_higher_risk(self, default_accel):
        default_accel.start_challenge()
        default_accel.update(equity_pct=1.0, day=3)
        assert default_accel.get_risk_multiplier() == PHASE_PROFILES["ATTACK"]["risk_multiplier"]
        assert default_accel.get_risk_multiplier() > 1.0

    def test_coast_lower_risk(self, default_accel):
        default_accel.start_challenge()
        default_accel.update(equity_pct=9.5, day=15)
        assert default_accel.get_risk_multiplier() == PHASE_PROFILES["COAST"]["risk_multiplier"]
        assert default_accel.get_risk_multiplier() < 1.0

    def test_effective_risk_combines_multipliers(self, default_accel):
        default_accel.start_challenge()
        default_accel.update(equity_pct=1.0, day=3)
        base_risk = 1.5
        adaptive_mult = 1.3
        result = default_accel.get_effective_risk(base_risk, adaptive_mult)
        expected = base_risk * adaptive_mult * PHASE_PROFILES["ATTACK"]["risk_multiplier"]
        assert abs(result - expected) < 0.001


class TestTradeTracking:
    def test_trade_count(self, default_accel):
        default_accel.start_challenge()
        default_accel.record_trade("2026-01-01")
        default_accel.record_trade("2026-01-01")
        assert default_accel._state.trades_taken == 2

    def test_daily_trade_limit(self, default_accel):
        default_accel.start_challenge()
        default_accel.update(equity_pct=9.5, day=20)  # COAST -> max 1/day
        default_accel.record_trade("2026-01-20")
        assert not default_accel.can_trade_today("2026-01-20")

    def test_attack_more_trades_allowed(self, default_accel):
        default_accel.start_challenge()
        default_accel.update(equity_pct=1.0, day=3)  # ATTACK -> max 5/day
        for i in range(4):
            default_accel.record_trade("2026-01-03")
        assert default_accel.can_trade_today("2026-01-03")


class TestStatus:
    def test_status_dict(self, default_accel):
        default_accel.start_challenge()
        default_accel.update(equity_pct=5.0, day=10)
        status = default_accel.get_status()
        assert "phase" in status
        assert "day" in status
        assert "progress" in status
        assert status["is_funded"] is False
