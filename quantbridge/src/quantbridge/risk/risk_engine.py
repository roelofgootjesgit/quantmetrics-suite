from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, Optional


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(float(value), maximum))


def drawdown_pct(reference_balance: float, current_equity: float) -> float:
    ref = float(reference_balance)
    if ref <= 0:
        return 0.0
    dd = (ref - float(current_equity)) / ref * 100.0
    return max(0.0, dd)


@dataclass(frozen=True)
class TradeIntent:
    instrument: str
    direction: str
    units: float
    risk_per_trade_pct: Optional[float] = None


@dataclass(frozen=True)
class RiskSnapshot:
    equity: float
    start_of_day_balance: float
    start_balance: float
    open_positions: int
    open_risk_pct: float = 0.0
    symbol_exposure_pct: Dict[str, float] = field(default_factory=dict)
    trading_paused: bool = False
    account_breached: bool = False


@dataclass(frozen=True)
class RiskDecision:
    allowed: bool
    adjusted_units: float
    reason: str
    code: str = "ok"
    trigger_failsafe: bool = False
    metrics: Dict[str, float] = field(default_factory=dict)
    timestamp: str = field(default_factory=_utc_now_iso)
