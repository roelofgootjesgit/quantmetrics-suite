"""Signal and entry candidate models."""
from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class SignalStrength(str, Enum):
    STRONG = "strong"
    MODERATE = "moderate"
    WEAK = "weak"


class Signal(BaseModel):
    """A trading signal from the strategy layer."""
    timestamp: datetime
    direction: str
    strength: SignalStrength = SignalStrength.MODERATE
    modules_fired: list[str] = Field(default_factory=list)
    structure_label: str = ""
    regime: Optional[str] = None
    news_sentiment: Optional[str] = None
    news_boost: float = 1.0
    confidence: float = Field(ge=0.0, le=1.0, default=0.5)


class EntryCandidate(BaseModel):
    """An entry candidate after all filters are applied."""
    signal: Signal
    atr: float
    tp_price: float
    sl_price: float
    position_size: float = 0.0
    risk_pct: float = 0.01
    blocked_reason: Optional[str] = None

    @property
    def is_allowed(self) -> bool:
        return self.blocked_reason is None
