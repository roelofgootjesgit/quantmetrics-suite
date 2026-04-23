from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Literal, Optional

from quantbridge.accounts.account_state_store import AccountStateStore

AccountStatus = Literal["demo", "challenge", "funded", "paused", "breached", "disabled"]


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class AccountState:
    account_id: str
    status: AccountStatus
    reason: str = ""
    paused_by: str = ""
    breach_type: str = ""
    last_health_state: str = ""
    last_risk_block: str = ""
    updated_at: str = field(default_factory=_utc_now_iso)


class AccountStateMachine:
    """Persisted account state transitions for routing + safety decisions."""

    def __init__(self, path: str | Path = "state/account_states.json") -> None:
        self.path = Path(path)
        self.store = AccountStateStore(path=self.path)

    def get_state(self, account_id: str, default_status: AccountStatus = "demo") -> AccountState:
        raw = self.store.load()
        entry = raw.get(str(account_id), {})
        status = str(entry.get("status", default_status))
        reason = str(entry.get("reason", ""))
        paused_by = str(entry.get("paused_by", ""))
        breach_type = str(entry.get("breach_type", ""))
        last_health_state = str(entry.get("last_health_state", ""))
        last_risk_block = str(entry.get("last_risk_block", ""))
        updated_at = str(entry.get("updated_at", _utc_now_iso()))
        return AccountState(
            account_id=str(account_id),
            status=status,  # type: ignore[arg-type]
            reason=reason,
            paused_by=paused_by,
            breach_type=breach_type,
            last_health_state=last_health_state,
            last_risk_block=last_risk_block,
            updated_at=updated_at,
        )

    def set_state(
        self,
        account_id: str,
        status: AccountStatus,
        reason: str = "",
        paused_by: str = "",
        breach_type: str = "",
        last_health_state: str = "",
        last_risk_block: str = "",
    ) -> AccountState:
        raw = self.store.load()
        state = AccountState(
            account_id=str(account_id),
            status=status,
            reason=reason,
            paused_by=paused_by,
            breach_type=breach_type,
            last_health_state=last_health_state,
            last_risk_block=last_risk_block,
        )
        raw[str(account_id)] = {
            "status": state.status,
            "reason": state.reason,
            "paused_by": state.paused_by,
            "breach_type": state.breach_type,
            "last_health_state": state.last_health_state,
            "last_risk_block": state.last_risk_block,
            "updated_at": state.updated_at,
        }
        self.store.save(raw)
        return state

    def pause(self, account_id: str, reason: str, paused_by: str = "runtime_failsafe") -> AccountState:
        previous = self.get_state(account_id=account_id)
        return self.set_state(
            account_id=account_id,
            status="paused",
            reason=reason,
            paused_by=paused_by,
            breach_type=previous.breach_type,
            last_health_state=previous.last_health_state,
            last_risk_block=previous.last_risk_block,
        )

    def breach(self, account_id: str, reason: str, breach_type: str = "unknown") -> AccountState:
        previous = self.get_state(account_id=account_id)
        return self.set_state(
            account_id=account_id,
            status="breached",
            reason=reason,
            paused_by=previous.paused_by,
            breach_type=breach_type,
            last_health_state=previous.last_health_state,
            last_risk_block=previous.last_risk_block,
        )

    def resume(self, account_id: str, mode: Literal["demo", "challenge", "funded"], reason: str = "") -> AccountState:
        previous = self.get_state(account_id=account_id)
        return self.set_state(
            account_id=account_id,
            status=mode,
            reason=reason,
            paused_by=previous.paused_by,
            breach_type=previous.breach_type,
            last_health_state=previous.last_health_state,
            last_risk_block=previous.last_risk_block,
        )

    def set_health_state(self, account_id: str, health_state: str, reason: str = "") -> AccountState:
        previous = self.get_state(account_id=account_id)
        return self.set_state(
            account_id=account_id,
            status=previous.status,
            reason=reason or previous.reason,
            paused_by=previous.paused_by,
            breach_type=previous.breach_type,
            last_health_state=health_state,
            last_risk_block=previous.last_risk_block,
        )

    def record_risk_block(self, account_id: str, block_reason: str) -> AccountState:
        previous = self.get_state(account_id=account_id)
        return self.set_state(
            account_id=account_id,
            status=previous.status,
            reason=previous.reason,
            paused_by=previous.paused_by,
            breach_type=previous.breach_type,
            last_health_state=previous.last_health_state,
            last_risk_block=block_reason,
        )

    def is_eligible_for_trading(self, account_id: str, default_status: AccountStatus = "demo") -> bool:
        state = self.get_state(account_id=account_id, default_status=default_status)
        return state.status in {"demo", "challenge", "funded"}

    def get_pause_reason(self, account_id: str) -> Optional[str]:
        state = self.get_state(account_id=account_id)
        if state.status in {"paused", "breached", "disabled"}:
            return state.reason or state.status
        return None

