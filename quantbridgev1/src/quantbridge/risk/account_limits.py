from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AccountLimits:
    daily_drawdown_limit_pct: float = 5.0
    total_drawdown_limit_pct: float = 10.0
    max_open_risk_pct: float = 3.0
    max_risk_per_trade_pct: float = 1.0
    max_concurrent_positions: int = 3
    symbol_exposure_limit_pct: float = 2.0
    min_units_per_trade: float = 1.0
    max_units_per_trade: float = 1000.0
