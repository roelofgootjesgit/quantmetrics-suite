from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from quantbridge.risk.account_limits import AccountLimits

AccountMode = Literal["demo", "challenge", "funded"]
RoutingMode = Literal["primary", "backup", "fanout"]


@dataclass(frozen=True)
class AccountPolicy:
    account_id: str
    mode: AccountMode = "demo"
    enabled: bool = True
    priority: int = 100
    routing_mode: RoutingMode = "primary"
    account_group: str = "default"
    sizing_multiplier: float = 1.0
    allowed_symbols: list[str] = field(default_factory=list)
    limits: AccountLimits = field(default_factory=AccountLimits)

