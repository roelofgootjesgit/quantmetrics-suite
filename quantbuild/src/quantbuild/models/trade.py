"""Typed trade and position models."""
from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class TradeDirection(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"


class TradeResult(str, Enum):
    WIN = "WIN"
    LOSS = "LOSS"
    TIMEOUT = "TIMEOUT"


class Trade(BaseModel):
    """Single trade result from backtest or live execution."""
    timestamp_open: datetime
    timestamp_close: datetime
    symbol: str
    direction: TradeDirection
    entry_price: float
    exit_price: float
    sl: float
    tp: float
    profit_usd: float
    profit_r: float
    result: TradeResult
    regime: Optional[str] = None
    session: Optional[str] = None
    sentiment_score: Optional[float] = None
    news_proximity_min: Optional[float] = None
    spread_at_entry: Optional[float] = None
    news_sentiment_at_entry: Optional[str] = Field(
        None, description="bullish/bearish/neutral from news layer"
    )
    news_boost_applied: Optional[float] = Field(
        None, description="Position size multiplier from news sentiment"
    )


class Position(BaseModel):
    """Live open position being tracked."""
    trade_id: str
    instrument: str
    direction: TradeDirection
    entry_price: float
    units: float
    current_price: float = 0.0
    unrealized_pnl: float = 0.0
    sl: float
    tp: float
    open_time: datetime
    atr_at_entry: float = 0.0
    regime_at_entry: str = ""
    thesis: str = Field("", description="Why we entered this trade")
    thesis_valid: bool = True
    partial_closed: bool = False
    break_even_set: bool = False
    trailing_active: bool = False
    peak_price: float = 0.0


def calculate_rr(entry: float, exit_price: float, sl: float, direction: str) -> float:
    """Calculate risk-reward ratio for a trade."""
    if direction == "LONG":
        risk = abs(entry - sl)
        profit = exit_price - entry
    else:
        risk = abs(sl - entry)
        profit = entry - exit_price
    return (profit / risk) if risk else 0.0
