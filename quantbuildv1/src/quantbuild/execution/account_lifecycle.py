"""Account Lifecycle Manager — orchestrates CHALLENGE -> FUNDED transitions.

Deployment Blueprint v1 defines two operational envelopes:
  CHALLENGE: Core + NAS100 + Pass Accelerator (high throughput, aggressive)
  FUNDED:    Core + EURUSD MR (capital preservation, income generation)

This manager:
  1. Tracks account equity, DD, and phase for each trading account
  2. Auto-switches instrument/risk profiles when challenge is passed
  3. Enforces kill switches per account type
  4. Manages multi-account scaling (parallel funded + challenge accounts)
"""
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class AccountType(str, Enum):
    CHALLENGE = "challenge"
    FUNDED = "funded"


class AccountStatus(str, Enum):
    ACTIVE = "active"
    PASSED = "passed"
    FAILED = "failed"
    HALTED = "halted"  # kill-switch triggered, manual review needed
    RETIRED = "retired"


@dataclass
class AccountState:
    account_id: str
    account_type: AccountType
    status: AccountStatus = AccountStatus.ACTIVE
    start_date: Optional[datetime] = None

    starting_balance: float = 100_000.0
    current_equity: float = 100_000.0
    peak_equity: float = 100_000.0

    total_pnl: float = 0.0
    total_trades: int = 0
    daily_pnl: float = 0.0
    consecutive_losing_days: int = 0

    payout_total: float = 0.0
    months_funded: int = 0

    created_at: Optional[datetime] = None
    passed_at: Optional[datetime] = None
    funded_at: Optional[datetime] = None
    halted_at: Optional[datetime] = None

    halt_reason: str = ""
    notes: List[str] = field(default_factory=list)


class AccountLifecycleManager:
    """Manages one or more trading accounts through their lifecycle.

    Usage:
        mgr = AccountLifecycleManager(challenge_config, funded_config)
        mgr.create_account("ftmo-001", AccountType.CHALLENGE)

        # After each trade:
        mgr.record_trade("ftmo-001", pnl_dollars=350.0)

        # Daily check:
        result = mgr.daily_check("ftmo-001")
        if result["action"] == "SWITCH_TO_FUNDED":
            # System auto-switches config
            ...
    """

    def __init__(self, challenge_config: Dict, funded_config: Dict):
        self._challenge_cfg = challenge_config
        self._funded_cfg = funded_config
        self._accounts: Dict[str, AccountState] = {}

    @property
    def accounts(self) -> Dict[str, AccountState]:
        return dict(self._accounts)

    def create_account(
        self,
        account_id: str,
        account_type: AccountType,
        starting_balance: float = 100_000.0,
    ) -> AccountState:
        now = datetime.utcnow()
        state = AccountState(
            account_id=account_id,
            account_type=account_type,
            starting_balance=starting_balance,
            current_equity=starting_balance,
            peak_equity=starting_balance,
            start_date=now,
            created_at=now,
        )
        self._accounts[account_id] = state
        logger.info("Account created: %s (%s) balance=%.0f",
                     account_id, account_type.value, starting_balance)
        return state

    def get_active_config(self, account_id: str) -> Dict:
        """Return the correct config envelope for this account's current type."""
        state = self._accounts[account_id]
        if state.account_type == AccountType.FUNDED:
            return self._funded_cfg
        return self._challenge_cfg

    def get_enabled_instruments(self, account_id: str) -> Dict[str, Dict]:
        """Return only enabled instruments for this account's config."""
        cfg = self.get_active_config(account_id)
        instruments = cfg.get("instruments", {})
        return {k: v for k, v in instruments.items() if v.get("enabled", True)}

    def record_trade(self, account_id: str, pnl_dollars: float, symbol: str = ""):
        """Record a completed trade and check kill switches."""
        state = self._accounts[account_id]
        if state.status != AccountStatus.ACTIVE:
            logger.warning("Trade on non-active account %s (status=%s)",
                          account_id, state.status.value)
            return

        state.current_equity += pnl_dollars
        state.total_pnl += pnl_dollars
        state.daily_pnl += pnl_dollars
        state.total_trades += 1
        state.peak_equity = max(state.peak_equity, state.current_equity)

    def start_new_day(self, account_id: str):
        """Reset daily counters; track consecutive losing days."""
        state = self._accounts[account_id]
        if state.daily_pnl < 0:
            state.consecutive_losing_days += 1
        else:
            state.consecutive_losing_days = 0
        state.daily_pnl = 0.0

    def daily_check(self, account_id: str) -> Dict[str, Any]:
        """Run kill-switch checks and lifecycle transitions.

        Returns a dict with 'action' key:
          CONTINUE      — keep trading
          HALT          — kill switch triggered, stop trading
          SWITCH_TO_FUNDED — challenge passed, switch config
          FAILED        — challenge failed (DD limit or timeout)
        """
        state = self._accounts[account_id]
        if state.status != AccountStatus.ACTIVE:
            return {"action": "HALT", "reason": f"Account {state.status.value}"}

        cfg = self.get_active_config(account_id)
        kills = cfg.get("kill_switches", {})

        dd_pct = self._drawdown_pct(state)
        equity_change_pct = self._equity_change_pct(state)
        daily_loss_pct = abs(min(0, state.daily_pnl) / state.starting_balance * 100)

        result: Dict[str, Any] = {"action": "CONTINUE", "dd_pct": round(dd_pct, 2)}

        if state.account_type == AccountType.CHALLENGE:
            result.update(self._check_challenge(state, kills, equity_change_pct, dd_pct))
        else:
            result.update(self._check_funded(state, kills, dd_pct, daily_loss_pct))

        return result

    def _check_challenge(
        self, state: AccountState, kills: Dict, equity_change_pct: float, dd_pct: float
    ) -> Dict[str, Any]:
        target_pct = 10.0
        max_dd = kills.get("max_total_dd_pct", 10.0)
        reset_dd = kills.get("challenge_reset_dd_pct", 8.0)

        if equity_change_pct >= target_pct:
            return self._pass_challenge(state)

        if dd_pct >= reset_dd:
            state.status = AccountStatus.FAILED
            state.halt_reason = f"DD {dd_pct:.1f}% exceeded reset threshold {reset_dd}%"
            logger.warning("Challenge FAILED: %s — %s", state.account_id, state.halt_reason)
            return {"action": "FAILED", "reason": state.halt_reason}

        if state.start_date:
            days_elapsed = (datetime.utcnow() - state.start_date).days
            if days_elapsed > 30:
                state.status = AccountStatus.FAILED
                state.halt_reason = f"Challenge timeout after {days_elapsed} days"
                logger.warning("Challenge TIMEOUT: %s", state.account_id)
                return {"action": "FAILED", "reason": state.halt_reason}

        return {"action": "CONTINUE"}

    def _pass_challenge(self, state: AccountState) -> Dict[str, Any]:
        """Handle challenge pass -> switch to funded."""
        state.status = AccountStatus.PASSED
        state.passed_at = datetime.utcnow()
        state.notes.append(
            f"Challenge passed: +{self._equity_change_pct(state):.1f}% "
            f"in {state.total_trades} trades"
        )
        logger.info("CHALLENGE PASSED: %s — switching to FUNDED", state.account_id)

        new_id = f"{state.account_id}-funded"
        funded = self.create_account(
            new_id, AccountType.FUNDED, state.current_equity
        )
        funded.funded_at = datetime.utcnow()
        funded.notes.append(f"Graduated from challenge {state.account_id}")

        return {
            "action": "SWITCH_TO_FUNDED",
            "reason": "Challenge target reached",
            "new_account_id": new_id,
        }

    def _check_funded(
        self, state: AccountState, kills: Dict, dd_pct: float, daily_loss_pct: float
    ) -> Dict[str, Any]:
        max_dd = kills.get("max_total_dd_pct", 5.0)
        max_daily = kills.get("max_daily_loss_pct", 2.0)
        losing_days_halt = kills.get("consecutive_losing_days_halt", 3)

        if dd_pct >= max_dd:
            state.status = AccountStatus.HALTED
            state.halted_at = datetime.utcnow()
            state.halt_reason = f"Funded DD {dd_pct:.1f}% >= {max_dd}%"
            logger.warning("FUNDED HALTED: %s — %s", state.account_id, state.halt_reason)
            return {"action": "HALT", "reason": state.halt_reason}

        if daily_loss_pct >= max_daily:
            return {
                "action": "HALT",
                "reason": f"Daily loss {daily_loss_pct:.1f}% >= {max_daily}% — stop for today",
                "duration": "end_of_day",
            }

        if state.consecutive_losing_days >= losing_days_halt:
            return {
                "action": "CONTINUE",
                "risk_override": 0.5,
                "reason": f"{state.consecutive_losing_days} losing days — risk halved",
            }

        return {"action": "CONTINUE"}

    def record_payout(self, account_id: str, amount: float):
        state = self._accounts[account_id]
        state.payout_total += amount
        state.months_funded += 1
        state.notes.append(f"Payout #{state.months_funded}: ${amount:,.0f}")
        logger.info("Payout recorded: %s — $%.0f (total: $%.0f)",
                     account_id, amount, state.payout_total)

    def get_portfolio_summary(self) -> Dict[str, Any]:
        """High-level dashboard of all accounts."""
        active_challenge = []
        active_funded = []
        total_equity = 0.0
        total_payout = 0.0

        for aid, s in self._accounts.items():
            if s.status == AccountStatus.ACTIVE:
                if s.account_type == AccountType.CHALLENGE:
                    active_challenge.append({
                        "id": aid,
                        "equity": round(s.current_equity, 2),
                        "pnl_pct": round(self._equity_change_pct(s), 2),
                        "dd_pct": round(self._drawdown_pct(s), 2),
                        "trades": s.total_trades,
                    })
                else:
                    active_funded.append({
                        "id": aid,
                        "equity": round(s.current_equity, 2),
                        "pnl_pct": round(self._equity_change_pct(s), 2),
                        "dd_pct": round(self._drawdown_pct(s), 2),
                        "trades": s.total_trades,
                        "payouts": s.payout_total,
                    })
                total_equity += s.current_equity
            total_payout += s.payout_total

        return {
            "active_challenges": active_challenge,
            "active_funded": active_funded,
            "total_accounts": len(self._accounts),
            "total_equity": round(total_equity, 2),
            "total_payout": round(total_payout, 2),
            "scaling_phase": self._scaling_phase(len(active_funded), len(active_challenge)),
        }

    @staticmethod
    def _scaling_phase(funded: int, challenge: int) -> str:
        if funded == 0 and challenge <= 1:
            return "START"
        if funded <= 2:
            return "PASS_1"
        if funded <= 4:
            return "PASS_2"
        return "SCALE"

    @staticmethod
    def _drawdown_pct(state: AccountState) -> float:
        if state.peak_equity <= 0:
            return 0.0
        return (state.peak_equity - state.current_equity) / state.peak_equity * 100

    @staticmethod
    def _equity_change_pct(state: AccountState) -> float:
        if state.starting_balance <= 0:
            return 0.0
        return (state.current_equity - state.starting_balance) / state.starting_balance * 100
