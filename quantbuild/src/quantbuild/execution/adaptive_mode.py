"""Adaptive Mode Layer — dynamic risk scaling based on equity curve.

Instead of manually choosing CHALLENGE vs CONSISTENT, the system
scales risk automatically based on current performance state:

  AGGRESSIVE:  equity DD < 1%, recent momentum positive -> push harder
  BASE:        normal operation
  DEFENSIVE:   equity DD > 3% or losing streak -> reduce risk
  LOCKDOWN:    equity DD > 5% -> minimal risk, preservation only

This is how professional desks manage capital dynamically.
"""
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class ModeState:
    """Current adaptive mode state."""
    mode: str = "BASE"
    risk_multiplier: float = 1.0
    heat_multiplier: float = 1.0
    reason: str = ""
    since: Optional[datetime] = None
    consecutive_losses: int = 0
    consecutive_wins: int = 0


# Mode definitions with risk scaling
MODE_PROFILES = {
    "AGGRESSIVE": {
        "risk_multiplier": 1.3,
        "heat_multiplier": 1.2,
        "description": "Equity healthy, momentum positive — push harder",
    },
    "BASE": {
        # BASE acts as a cautious default: slightly below full risk
        # to avoid negative expectancy in "no-signal" equity states.
        "risk_multiplier": 0.85,
        "heat_multiplier": 0.9,
        "description": "Default cautious — no momentum signal",
    },
    "DEFENSIVE": {
        "risk_multiplier": 0.6,
        "heat_multiplier": 0.7,
        "description": "Drawdown detected — reduce risk",
    },
    "LOCKDOWN": {
        "risk_multiplier": 0.3,
        "heat_multiplier": 0.4,
        "description": "Severe drawdown — capital preservation",
    },
}


class AdaptiveModeLayer:
    """Dynamically adjusts risk parameters based on equity state.

    Equity-curve based position sizing:
    - When winning: scale up gradually (not recklessly)
    - When losing: scale down quickly (protect capital)

    This asymmetry is the key to professional risk management.
    """

    def __init__(self, config: Dict[str, Any]):
        cfg = config.get("adaptive_mode", {})

        # Thresholds for mode transitions
        self._aggressive_dd_max: float = cfg.get("aggressive_dd_max", 1.0)
        self._aggressive_momentum_window: int = cfg.get("aggressive_momentum_window", 5)
        self._defensive_dd: float = cfg.get("defensive_dd", 3.0)
        self._lockdown_dd: float = cfg.get("lockdown_dd", 5.0)
        self._defensive_losing_streak: int = cfg.get("defensive_losing_streak", 4)
        self._lockdown_losing_streak: int = cfg.get("lockdown_losing_streak", 6)

        # Recovery: how many wins needed to upgrade from DEFENSIVE
        self._recovery_wins: int = cfg.get("recovery_wins", 3)

        # State
        self._state = ModeState(mode="BASE", since=datetime.utcnow())
        self._equity_peak: float = 0.0
        self._equity_current: float = 0.0
        self._recent_results: List[float] = []
        self._trade_history: List[Dict] = []

    @property
    def state(self) -> ModeState:
        return self._state

    @property
    def current_mode(self) -> str:
        return self._state.mode

    @property
    def risk_multiplier(self) -> float:
        return self._state.risk_multiplier

    @property
    def heat_multiplier(self) -> float:
        return self._state.heat_multiplier

    def get_effective_risk(self, base_risk_pct: float) -> float:
        """Apply mode multiplier to base risk."""
        return base_risk_pct * self._state.risk_multiplier

    def get_effective_heat_limit(self, base_heat_pct: float) -> float:
        """Apply mode multiplier to heat limit."""
        return base_heat_pct * self._state.heat_multiplier

    def update_equity(self, equity_pct: float):
        """Update equity state and recalculate mode."""
        self._equity_current = equity_pct
        if equity_pct > self._equity_peak:
            self._equity_peak = equity_pct
        self._evaluate_mode()

    def record_trade(self, pnl_r: float, symbol: str = "", regime: str = ""):
        """Record a trade result and update mode."""
        self._recent_results.append(pnl_r)
        if len(self._recent_results) > 20:
            self._recent_results.pop(0)

        self._trade_history.append({
            "pnl_r": pnl_r, "symbol": symbol, "regime": regime,
            "mode": self._state.mode, "ts": datetime.utcnow(),
        })

        # Update streak
        if pnl_r > 0:
            self._state.consecutive_wins += 1
            self._state.consecutive_losses = 0
        elif pnl_r < 0:
            self._state.consecutive_losses += 1
            self._state.consecutive_wins = 0

        self._evaluate_mode()

    def _evaluate_mode(self):
        """Core mode evaluation logic."""
        dd_from_peak = self._equity_peak - self._equity_current
        old_mode = self._state.mode

        # LOCKDOWN: severe drawdown or extreme losing streak
        if dd_from_peak >= self._lockdown_dd or self._state.consecutive_losses >= self._lockdown_losing_streak:
            new_mode = "LOCKDOWN"
            reason = f"DD {dd_from_peak:.1f}% or {self._state.consecutive_losses} consecutive losses"

        # DEFENSIVE: moderate drawdown or losing streak
        elif dd_from_peak >= self._defensive_dd or self._state.consecutive_losses >= self._defensive_losing_streak:
            new_mode = "DEFENSIVE"
            reason = f"DD {dd_from_peak:.1f}% or {self._state.consecutive_losses} consecutive losses"

        # AGGRESSIVE: small DD + positive momentum
        elif dd_from_peak <= self._aggressive_dd_max and self._has_positive_momentum():
            # Only upgrade from BASE, never from DEFENSIVE without recovery
            if old_mode in ("BASE", "AGGRESSIVE"):
                new_mode = "AGGRESSIVE"
                reason = f"DD {dd_from_peak:.1f}%, momentum positive"
            elif old_mode == "DEFENSIVE" and self._state.consecutive_wins >= self._recovery_wins:
                new_mode = "BASE"
                reason = f"Recovery: {self._state.consecutive_wins} consecutive wins"
            else:
                new_mode = old_mode
                reason = self._state.reason

        # BASE: default
        else:
            if old_mode == "DEFENSIVE" and self._state.consecutive_wins >= self._recovery_wins:
                new_mode = "BASE"
                reason = f"Recovery from DEFENSIVE: {self._state.consecutive_wins} wins"
            elif old_mode == "LOCKDOWN" and self._state.consecutive_wins >= self._recovery_wins:
                new_mode = "DEFENSIVE"
                reason = f"Recovery from LOCKDOWN: {self._state.consecutive_wins} wins"
            elif old_mode in ("LOCKDOWN", "DEFENSIVE"):
                new_mode = old_mode
                reason = self._state.reason
            else:
                new_mode = "BASE"
                reason = "Normal"

        if new_mode != old_mode:
            profile = MODE_PROFILES[new_mode]
            self._state = ModeState(
                mode=new_mode,
                risk_multiplier=profile["risk_multiplier"],
                heat_multiplier=profile["heat_multiplier"],
                reason=reason,
                since=datetime.utcnow(),
                consecutive_losses=self._state.consecutive_losses,
                consecutive_wins=self._state.consecutive_wins,
            )
            logger.info("Mode switch: %s -> %s (%s)", old_mode, new_mode, reason)

    def _has_positive_momentum(self) -> bool:
        """Check if recent trades show positive momentum."""
        window = self._aggressive_momentum_window
        if len(self._recent_results) < window:
            return False
        recent = self._recent_results[-window:]
        return sum(recent) > 0 and sum(1 for r in recent if r > 0) >= window * 0.6

    def get_status(self) -> Dict[str, Any]:
        dd = self._equity_peak - self._equity_current
        return {
            "mode": self._state.mode,
            "risk_multiplier": self._state.risk_multiplier,
            "heat_multiplier": self._state.heat_multiplier,
            "reason": self._state.reason,
            "equity_dd": round(dd, 2),
            "consecutive_wins": self._state.consecutive_wins,
            "consecutive_losses": self._state.consecutive_losses,
            "recent_trades": len(self._recent_results),
        }
