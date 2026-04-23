from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Literal, Optional

from quantbridge.accounts.account_policy import AccountPolicy
from quantbridge.router.account_selector import AccountRuntimeStatus, AccountSelector

RoutingPolicyMode = Literal["single", "primary_backup", "fanout"]
PlanRole = Literal["primary", "backup", "fanout"]


@dataclass(frozen=True)
class TradeRequest:
    instrument: str
    direction: str
    units: float
    sl: Optional[float] = None
    tp: Optional[float] = None
    comment: str = ""
    client_order_ref: str = ""
    strategy: str = "unknown"
    account_group: str = "default"
    routing_mode: RoutingPolicyMode = "single"
    max_fanout_accounts: Optional[int] = None
    trace_id: str = ""
    # QuantLog correlation (QuantBuild ENTER / decision cycle); optional for standalone bridge runs.
    trade_id: str = ""
    decision_cycle_id: str = ""


@dataclass(frozen=True)
class ExecutionPlanItem:
    account_id: str
    role: PlanRole
    planned_units: float
    sizing_multiplier: float
    order_index: int
    selected_policy: AccountPolicy


@dataclass(frozen=True)
class ExecutionPlan:
    routing_mode: RoutingPolicyMode
    instrument: str
    direction: str
    items: list[ExecutionPlanItem] = field(default_factory=list)
    skipped: list[dict] = field(default_factory=list)


class ExecutionPlanBuilder:
    """Build account-level execution plans from policies + runtime eligibility."""

    def __init__(self, selector: AccountSelector) -> None:
        self.selector = selector

    def build(
        self,
        *,
        request: TradeRequest,
        policies: Iterable[AccountPolicy],
        unhealthy_account_ids: Iterable[str] | None = None,
        runtime_status_by_account: dict[str, AccountRuntimeStatus] | None = None,
    ) -> ExecutionPlan:
        account_group = str(request.account_group).strip().lower()
        filtered_policies = [
            policy
            for policy in policies
            if (str(policy.account_group).strip().lower() == account_group)
            or (account_group in {"", "default"})
        ]
        eligible, skipped = self.selector.rank_eligible(
            policies=filtered_policies,
            instrument=request.instrument,
            unhealthy_account_ids=unhealthy_account_ids,
            runtime_status_by_account=runtime_status_by_account,
        )

        items: list[ExecutionPlanItem] = []
        routing_mode: RoutingPolicyMode = request.routing_mode
        if routing_mode == "single":
            if eligible:
                policy = eligible[0]
                items.append(
                    ExecutionPlanItem(
                        account_id=policy.account_id,
                        role="primary",
                        planned_units=float(request.units) * float(policy.sizing_multiplier),
                        sizing_multiplier=float(policy.sizing_multiplier),
                        order_index=1,
                        selected_policy=policy,
                    )
                )
        elif routing_mode == "primary_backup":
            for idx, policy in enumerate(eligible):
                role: PlanRole = "primary" if idx == 0 else "backup"
                items.append(
                    ExecutionPlanItem(
                        account_id=policy.account_id,
                        role=role,
                        planned_units=float(request.units) * float(policy.sizing_multiplier),
                        sizing_multiplier=float(policy.sizing_multiplier),
                        order_index=idx + 1,
                        selected_policy=policy,
                    )
                )
        else:  # fanout
            candidates = eligible
            if request.max_fanout_accounts is not None:
                candidates = eligible[: max(0, int(request.max_fanout_accounts))]
            for idx, policy in enumerate(candidates):
                items.append(
                    ExecutionPlanItem(
                        account_id=policy.account_id,
                        role="fanout",
                        planned_units=float(request.units) * float(policy.sizing_multiplier),
                        sizing_multiplier=float(policy.sizing_multiplier),
                        order_index=idx + 1,
                        selected_policy=policy,
                    )
                )

        return ExecutionPlan(
            routing_mode=routing_mode,
            instrument=request.instrument,
            direction=request.direction,
            items=items,
            skipped=skipped,
        )

