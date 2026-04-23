from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

from quantbridge.execution.models import Position


def _as_float(value) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except Exception:
        return None


@dataclass(frozen=True)
class ReconcileActions:
    add: List[dict]
    remove: List[dict]
    update: List[dict]

    @property
    def is_noop(self) -> bool:
        return not (self.add or self.remove or self.update)


class StateValidator:
    """Reconcile local registry against broker positions."""

    def __init__(self, numeric_tolerance: float = 1e-6) -> None:
        self.numeric_tolerance = abs(float(numeric_tolerance))

    def _almost_equal(self, left, right) -> bool:
        lf = _as_float(left)
        rf = _as_float(right)
        if lf is None or rf is None:
            return left == right
        return abs(lf - rf) <= self.numeric_tolerance

    def reconcile(self, broker_positions: List[Position], local_positions: Dict[str, dict]) -> ReconcileActions:
        actions = ReconcileActions(add=[], remove=[], update=[])
        local_map = {str(symbol).upper(): payload for symbol, payload in local_positions.items()}
        broker_map = {str(position.instrument).upper(): position for position in broker_positions}

        for symbol, position in broker_map.items():
            if symbol not in local_map:
                actions.add.append(
                    {
                        "symbol": symbol,
                        "reason": "missing_local_position",
                        "broker_id": position.trade_id,
                    }
                )
                continue

            local_entry = local_map[symbol] or {}
            field_changes = {}
            if str(local_entry.get("broker_id", "")) != str(position.trade_id):
                field_changes["broker_id"] = {"local": local_entry.get("broker_id"), "broker": position.trade_id}
            if str(local_entry.get("direction", "")) != str(position.direction):
                field_changes["direction"] = {"local": local_entry.get("direction"), "broker": position.direction}
            if not self._almost_equal(local_entry.get("size"), position.units):
                field_changes["size"] = {"local": local_entry.get("size"), "broker": position.units}
            if not self._almost_equal(local_entry.get("entry"), position.entry_price):
                field_changes["entry"] = {"local": local_entry.get("entry"), "broker": position.entry_price}
            if not self._almost_equal(local_entry.get("sl"), position.sl):
                field_changes["sl"] = {"local": local_entry.get("sl"), "broker": position.sl}
            if not self._almost_equal(local_entry.get("tp"), position.tp):
                field_changes["tp"] = {"local": local_entry.get("tp"), "broker": position.tp}

            if field_changes:
                actions.update.append(
                    {
                        "symbol": symbol,
                        "reason": "field_mismatch",
                        "fields": field_changes,
                    }
                )

        for symbol, local_entry in local_map.items():
            if symbol in broker_map:
                continue
            actions.remove.append(
                {
                    "symbol": symbol,
                    "reason": "missing_broker_position",
                    "broker_id": local_entry.get("broker_id"),
                }
            )

        return actions
