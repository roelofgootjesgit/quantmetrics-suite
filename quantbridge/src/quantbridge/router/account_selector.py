from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from quantbridge.accounts.account_policy import AccountPolicy
from quantbridge.accounts.account_state_machine import AccountStateMachine


@dataclass(frozen=True)
class AccountSelection:
    account_id: str
    reason: str
    selected_policy: AccountPolicy
    skipped: list[dict]


@dataclass(frozen=True)
class AccountRuntimeStatus:
    broker_healthy: bool = True
    runtime_paused: bool = False
    has_credentials: bool = True
    open_positions: int = 0


class AccountSelector:
    """Choose an eligible account while respecting status and policy filters."""

    def __init__(self, state_machine: AccountStateMachine) -> None:
        self.state_machine = state_machine

    def select(
        self,
        *,
        policies: Iterable[AccountPolicy],
        instrument: str,
        unhealthy_account_ids: Iterable[str] | None = None,
        runtime_status_by_account: dict[str, AccountRuntimeStatus] | None = None,
    ) -> AccountSelection | None:
        eligible, skipped = self.rank_eligible(
            policies=policies,
            instrument=instrument,
            unhealthy_account_ids=unhealthy_account_ids,
            runtime_status_by_account=runtime_status_by_account,
        )
        if eligible:
            selected = eligible[0]
            return AccountSelection(
                account_id=selected.account_id,
                reason=f"eligible_{selected.routing_mode}",
                selected_policy=selected,
                skipped=skipped,
            )
        return None

    def rank_eligible(
        self,
        *,
        policies: Iterable[AccountPolicy],
        instrument: str,
        unhealthy_account_ids: Iterable[str] | None = None,
        runtime_status_by_account: dict[str, AccountRuntimeStatus] | None = None,
    ) -> tuple[list[AccountPolicy], list[dict]]:
        unhealthy = {str(account_id) for account_id in (unhealthy_account_ids or [])}
        runtime_map = runtime_status_by_account or {}
        instrument_key = str(instrument).upper()
        skipped: list[dict] = []
        eligible: list[AccountPolicy] = []

        ordered = sorted(policies, key=lambda p: p.priority)
        for policy in ordered:
            account_id = str(policy.account_id)
            if not policy.enabled:
                skipped.append({"account_id": account_id, "reason": "policy_disabled"})
                continue
            runtime = runtime_map.get(account_id, AccountRuntimeStatus())
            if not runtime.has_credentials:
                skipped.append({"account_id": account_id, "reason": "missing_credentials"})
                continue
            if account_id in unhealthy:
                skipped.append({"account_id": account_id, "reason": "broker_unhealthy"})
                continue
            if not runtime.broker_healthy:
                skipped.append({"account_id": account_id, "reason": "broker_unhealthy"})
                continue
            if runtime.runtime_paused:
                skipped.append({"account_id": account_id, "reason": "runtime_paused"})
                continue
            if policy.allowed_symbols and instrument_key not in {sym.upper() for sym in policy.allowed_symbols}:
                skipped.append({"account_id": account_id, "reason": "symbol_not_allowed"})
                continue
            if runtime.open_positions >= policy.limits.max_concurrent_positions:
                skipped.append({"account_id": account_id, "reason": "max_positions_reached"})
                continue
            if not self.state_machine.is_eligible_for_trading(account_id=account_id, default_status=policy.mode):
                state = self.state_machine.get_state(account_id=account_id, default_status=policy.mode)
                skipped.append({"account_id": account_id, "reason": f"state_{state.status}"})
                continue
            eligible.append(policy)
        return eligible, skipped

