from __future__ import annotations

from typing import Dict, List, Optional, Protocol

from quantbridge.execution.health import HealthReport
from quantbridge.execution.models import AccountState, OrderResult, Position


class BrokerContract(Protocol):
    @property
    def is_connected(self) -> bool:
        ...

    def connect(self) -> bool:
        ...

    def disconnect(self) -> None:
        ...

    def health_check(self) -> HealthReport:
        ...

    def get_current_price(self, instrument: Optional[str] = None) -> Optional[Dict[str, float]]:
        ...

    def submit_market_order(
        self,
        instrument: Optional[str] = None,
        direction: str = "BUY",
        units: float = 1.0,
        sl: Optional[float] = None,
        tp: Optional[float] = None,
        comment: str = "",
        client_order_ref: str = "",
    ) -> OrderResult:
        ...

    def modify_trade(self, trade_id: str, sl: Optional[float] = None, tp: Optional[float] = None) -> bool:
        ...

    def close_trade(self, trade_id: str, units: Optional[float] = None) -> bool:
        ...

    def get_open_trades(self, instrument: Optional[str] = None) -> List[Position]:
        ...

    def get_account_state(self) -> Optional[AccountState]:
        ...

    def sync_positions(self, instrument: Optional[str] = None) -> List[Position]:
        ...
