"""Strategy plugin interface (Layer 2). No broker calls — signals only."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, List, Sequence


@dataclass
class StrategySignal:
    """Minimal signal shape for the host; align with v1 `Signal` when wiring."""

    strategy_id: str
    timestamp: datetime
    direction: str
    symbol: str
    confidence: float = 0.5
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class StrategyContext:
    """Snapshot passed from the engine each decision tick (extend as needed)."""

    symbol: str
    account_id: str
    now: datetime
    config: dict[str, Any] = field(default_factory=dict)


class Strategy(ABC):
    """
    One plugin = one coherent strategy implementation.

    Subclasses must accept ``(strategy_id: str, config: dict | None = None)`` so
    ``orchestrator.loader.load_strategies`` can construct them from YAML.
    """

    def __init__(self, strategy_id: str, config: dict[str, Any] | None = None) -> None:
        self._strategy_id = strategy_id
        self._strategy_config = dict(config or {})

    @property
    def id(self) -> str:
        return self._strategy_id

    def strategy_config(self) -> dict[str, Any]:
        return self._strategy_config

    @abstractmethod
    def allowed_symbols(self) -> Sequence[str]: ...

    @abstractmethod
    def on_bar(self, ctx: StrategyContext) -> List[StrategySignal]: ...

    def on_tick(self, ctx: StrategyContext) -> List[StrategySignal]:
        return []

    def on_news(self, ctx: StrategyContext) -> List[StrategySignal]:
        return []
