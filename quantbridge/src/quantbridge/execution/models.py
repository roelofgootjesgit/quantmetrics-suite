from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Optional


@dataclass(frozen=True)
class AccountState:
    account_id: str
    balance: float
    equity: float
    unrealized_pnl: float
    margin_used: float
    margin_available: float
    open_trade_count: int
    currency: str = "USD"


@dataclass(frozen=True)
class Position:
    trade_id: str
    instrument: str
    direction: Literal["LONG", "SHORT"]
    units: float
    entry_price: float
    current_price: float
    unrealized_pnl: float
    sl: Optional[float] = None
    tp: Optional[float] = None
    open_time: Optional[datetime] = None


@dataclass(frozen=True)
class OrderResult:
    success: bool
    order_id: Optional[str] = None
    trade_id: Optional[str] = None
    fill_price: Optional[float] = None
    message: str = ""
    error_code: Optional[str] = None
    raw_response: Optional[dict] = None
