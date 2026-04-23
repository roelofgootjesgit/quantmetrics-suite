"""Pass Acceleration Layer — phase-based risk scaling for FTMO challenges.

The #1 bottleneck for FTMO is not risk — it's TEMPO.
49% of simulated failures are timeouts, not DD blows.

This layer sits ON TOP of the adaptive mode and adjusts behavior
based on where you are in the challenge timeline:

  Phase 1 (ATTACK):    Day 1-10  -> higher risk, more aggressive entries
  Phase 2 (SECURE):    Near target -> protect gains, reduce risk
  Phase 3 (COAST):     Target reached -> minimal risk, wait for close

After challenge is passed, switches to FUNDED mode with consistent profile.

The key insight: early in a challenge, time is your enemy.
Late in a challenge, drawdown is your enemy.
Different phases need different risk envelopes.
"""
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


@dataclass
class ChallengeState:
    """Current challenge phase and metrics."""
    phase: str = "ATTACK"
    day: int = 0
    equity_pct: float = 0.0
    peak_equity_pct: float = 0.0
    target_pct: float = 10.0
    max_daily_loss_pct: float = 5.0
    max_total_dd_pct: float = 10.0
    trades_taken: int = 0
    start_date: Optional[datetime] = None


# Phase definitions
PHASE_PROFILES = {
    "ATTACK": {
        "risk_multiplier": 1.3,
        "heat_multiplier": 1.2,
        "max_trades_per_day": 5,
        "description": "Early challenge — push for target, time is the enemy",
    },
    "NORMAL": {
        "risk_multiplier": 1.0,
        "heat_multiplier": 1.0,
        "max_trades_per_day": 4,
        "description": "Mid challenge — normal operation",
    },
    "SECURE": {
        "risk_multiplier": 0.7,
        "heat_multiplier": 0.8,
        "max_trades_per_day": 3,
        "description": "Near target — protect gains",
    },
    "COAST": {
        "risk_multiplier": 0.3,
        "heat_multiplier": 0.4,
        "max_trades_per_day": 1,
        "description": "Target reached — minimal risk, wait for close",
    },
    "FUNDED": {
        "risk_multiplier": 0.75,
        "heat_multiplier": 0.8,
        "max_trades_per_day": 4,
        "description": "Funded account — consistent, capital preservation",
    },
}


class PassAccelerator:
    """Phase-based risk overlay for FTMO challenge optimization.

    Sits on top of AdaptiveModeLayer. The final risk multiplier is:
        effective_risk = base_risk * adaptive_mult * accelerator_mult

    Usage:
        accel = PassAccelerator(config)
        accel.start_challenge()

        # Each day:
        accel.update(current_equity_pct, day_number)
        risk_mult = accel.get_risk_multiplier()
    """

    def __init__(self, config: Dict[str, Any]):
        cfg = config.get("pass_accelerator", {})

        self._target_pct: float = cfg.get("target_pct", 10.0)
        self._max_daily_loss: float = cfg.get("max_daily_loss_pct", 5.0)
        self._max_total_dd: float = cfg.get("max_total_dd_pct", 10.0)
        self._challenge_days: int = cfg.get("challenge_days", 30)

        # Phase transition thresholds
        self._attack_until_day: int = cfg.get("attack_until_day", 10)
        self._secure_at_pct: float = cfg.get("secure_at_pct", 7.0)
        self._coast_at_pct: float = cfg.get("coast_at_pct", 9.0)

        # Safety: how close to DD limit before forcing defensive
        self._dd_danger_zone: float = cfg.get("dd_danger_zone_pct", 3.0)

        self._state = ChallengeState(
            target_pct=self._target_pct,
            max_daily_loss_pct=self._max_daily_loss,
            max_total_dd_pct=self._max_total_dd,
        )
        self._is_funded = False
        self._daily_trades: Dict[str, int] = {}

    @property
    def phase(self) -> str:
        return self._state.phase

    @property
    def is_funded(self) -> bool:
        return self._is_funded

    def start_challenge(self, start_date: Optional[datetime] = None):
        """Initialize a new challenge attempt."""
        self._state = ChallengeState(
            phase="ATTACK",
            start_date=start_date or datetime.utcnow(),
            target_pct=self._target_pct,
            max_daily_loss_pct=self._max_daily_loss,
            max_total_dd_pct=self._max_total_dd,
        )
        self._is_funded = False
        self._daily_trades = {}
        logger.info("Challenge started — Phase: ATTACK")

    def switch_to_funded(self):
        """Switch to funded mode after passing challenge."""
        self._is_funded = True
        self._state.phase = "FUNDED"
        logger.info("Switched to FUNDED mode")

    def update(self, equity_pct: float, day: int = 0, daily_pnl_pct: float = 0.0):
        """Update state and recalculate phase."""
        self._state.equity_pct = equity_pct
        self._state.peak_equity_pct = max(self._state.peak_equity_pct, equity_pct)
        self._state.day = day

        if self._is_funded:
            self._state.phase = "FUNDED"
            return

        dd_from_peak = self._state.peak_equity_pct - equity_pct

        old_phase = self._state.phase
        new_phase = self._evaluate_phase(equity_pct, day, dd_from_peak)

        if new_phase != old_phase:
            self._state.phase = new_phase
            logger.info("Challenge phase: %s -> %s (day %d, eq %.1f%%)",
                        old_phase, new_phase, day, equity_pct)

    def _evaluate_phase(self, equity_pct: float, day: int, dd_from_peak: float) -> str:
        # DD danger zone overrides everything
        remaining_dd = self._max_total_dd - dd_from_peak
        if remaining_dd <= self._dd_danger_zone:
            return "SECURE"

        # Target nearly reached
        if equity_pct >= self._coast_at_pct:
            return "COAST"

        # Getting close to target
        if equity_pct >= self._secure_at_pct:
            return "SECURE"

        # Early in challenge with room to be aggressive
        if day <= self._attack_until_day and dd_from_peak < self._max_total_dd * 0.3:
            return "ATTACK"

        # Late in challenge, still far from target -> push harder
        remaining_days = self._challenge_days - day
        if remaining_days <= 10 and equity_pct < self._target_pct * 0.5:
            return "ATTACK"

        return "NORMAL"

    def get_risk_multiplier(self) -> float:
        """Get the phase-based risk multiplier."""
        profile = PHASE_PROFILES.get(self._state.phase, PHASE_PROFILES["NORMAL"])
        return profile["risk_multiplier"]

    def get_heat_multiplier(self) -> float:
        profile = PHASE_PROFILES.get(self._state.phase, PHASE_PROFILES["NORMAL"])
        return profile["heat_multiplier"]

    def can_trade_today(self, date_str: str) -> bool:
        """Check if max trades per day for current phase is reached."""
        profile = PHASE_PROFILES.get(self._state.phase, PHASE_PROFILES["NORMAL"])
        max_today = profile["max_trades_per_day"]
        taken = self._daily_trades.get(date_str, 0)
        return taken < max_today

    def record_trade(self, date_str: str):
        self._daily_trades[date_str] = self._daily_trades.get(date_str, 0) + 1
        self._state.trades_taken += 1

    def get_effective_risk(self, base_risk: float, adaptive_multiplier: float = 1.0) -> float:
        """Final risk = base * adaptive * accelerator."""
        return base_risk * adaptive_multiplier * self.get_risk_multiplier()

    def get_status(self) -> Dict[str, Any]:
        return {
            "phase": self._state.phase,
            "day": self._state.day,
            "equity_pct": round(self._state.equity_pct, 2),
            "target_pct": self._target_pct,
            "progress": round(100 * self._state.equity_pct / self._target_pct, 1) if self._target_pct else 0,
            "risk_multiplier": self.get_risk_multiplier(),
            "trades_taken": self._state.trades_taken,
            "is_funded": self._is_funded,
        }
