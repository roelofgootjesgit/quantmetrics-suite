"""Placeholder strategy for wiring tests (never emits signals by default)."""
from __future__ import annotations

from datetime import datetime
from typing import List, Sequence

from quantbuild_v2.strategies.base import Strategy, StrategyContext, StrategySignal


class NoopStrategy(Strategy):
    """Returns no signals unless ``emit_test_signal: true`` in strategy config."""

    def allowed_symbols(self) -> Sequence[str]:
        return list(self.strategy_config().get("symbols") or ("XAUUSD",))

    def on_bar(self, ctx: StrategyContext) -> List[StrategySignal]:
        if not self.strategy_config().get("emit_test_signal"):
            return []
        return [
            StrategySignal(
                strategy_id=self.id,
                timestamp=ctx.now,
                direction="flat",
                symbol=ctx.symbol,
                confidence=0.0,
                meta={"note": "test"},
            )
        ]
