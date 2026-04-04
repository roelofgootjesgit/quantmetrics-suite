"""Strategy-layer decision contract (portable to a future ``quantstrategy`` package)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict


@dataclass
class SignalDecision:
    """What the strategy layer returns; execution maps this to QuantLog events."""

    action: str  # ENTER / EXIT / NO_ACTION
    direction: str  # LONG / SHORT / NONE
    confidence: float  # 0.0 - 1.0
    decision_context: Dict[str, Any] = field(default_factory=dict)
