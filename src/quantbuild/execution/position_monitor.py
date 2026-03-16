"""Position monitor — tracks open positions and triggers counter-news checks."""
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from src.quantbuild.models.trade import Position

logger = logging.getLogger(__name__)


class PositionMonitor:
    def __init__(self, cfg: dict[str, Any]):
        self._positions: Dict[str, Position] = {}

    def add_position(self, position: Position) -> None:
        self._positions[position.trade_id] = position
        logger.info("Tracking position: %s %s @ %.2f", position.trade_id, position.direction, position.entry_price)

    def remove_position(self, trade_id: str) -> Optional[Position]:
        pos = self._positions.pop(trade_id, None)
        if pos:
            logger.info("Removed position: %s", trade_id)
        return pos

    def update_price(self, trade_id: str, current_price: float) -> None:
        pos = self._positions.get(trade_id)
        if not pos:
            return
        pos.current_price = current_price
        if pos.direction == "LONG":
            pos.unrealized_pnl = (current_price - pos.entry_price) * pos.units
        else:
            pos.unrealized_pnl = (pos.entry_price - current_price) * pos.units
        if current_price > pos.peak_price:
            pos.peak_price = current_price

    def invalidate_thesis(self, trade_id: str, reason: str) -> None:
        pos = self._positions.get(trade_id)
        if pos:
            pos.thesis_valid = False
            logger.warning("Thesis invalidated for %s: %s", trade_id, reason)

    def weaken_thesis(self, trade_id: str, reason: str) -> None:
        pos = self._positions.get(trade_id)
        if pos:
            logger.info("Thesis weakened for %s: %s", trade_id, reason)

    @property
    def open_positions(self) -> List[Position]:
        return [p for p in self._positions.values() if p.thesis_valid]

    @property
    def all_positions(self) -> List[Position]:
        return list(self._positions.values())

    def get_summary(self) -> dict:
        total_pnl = sum(p.unrealized_pnl for p in self._positions.values())
        return {
            "open_count": len(self._positions),
            "total_unrealized_pnl": total_pnl,
            "positions": [
                {"trade_id": p.trade_id, "direction": p.direction.value if hasattr(p.direction, 'value') else p.direction,
                 "entry": p.entry_price, "current": p.current_price, "pnl": p.unrealized_pnl, "thesis_valid": p.thesis_valid}
                for p in self._positions.values()
            ],
        }
