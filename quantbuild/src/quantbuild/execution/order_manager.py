"""Order Manager — manages live order lifecycle with trailing stops, break-even, partial close."""
import json
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Literal, Optional

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[3]
STATE_FILE = ROOT / "data" / "state.json"


@dataclass
class ManagedOrder:
    trade_id: str
    instrument: str
    direction: Literal["LONG", "SHORT"]
    entry_price: float
    units: float
    original_sl: float
    original_tp: float
    current_sl: float
    current_tp: float
    open_time: datetime
    atr_at_entry: float = 0.0
    regime_at_entry: str = ""
    partial_closed: bool = False
    break_even_set: bool = False
    trailing_active: bool = False
    peak_price: float = 0.0
    slippage: float = 0.0


DEFAULT_ORDER_CONFIG = {
    "trailing_stop": {"enabled": True, "activation_r": 1.5, "trail_distance_r": 1.0},
    "break_even": {"enabled": True, "trigger_r": 1.0, "offset_pips": 2},
    "partial_close": {"enabled": True, "trigger_r": 1.0, "close_pct": 50},
}


class OrderManager:
    def __init__(self, broker=None, config: Optional[Dict] = None):
        self.broker = broker
        self.config = {**DEFAULT_ORDER_CONFIG, **(config or {})}
        self.managed_orders: Dict[str, ManagedOrder] = {}
        self._callbacks: List[Callable] = []

    def add_callback(self, callback: Callable[[str, ManagedOrder, Dict], None]) -> None:
        self._callbacks.append(callback)

    def _notify(self, event: str, order: ManagedOrder, details: Dict = None) -> None:
        for cb in self._callbacks:
            try:
                cb(event, order, details or {})
            except Exception as e:
                logger.warning("Callback error: %s", e)

    def register_trade(self, trade_id: str, instrument: str, direction: str,
                       entry_price: float, units: float, sl: float, tp: float,
                       atr: float = 0.0, regime: str = "", requested_price: float = 0.0) -> ManagedOrder:
        order = ManagedOrder(
            trade_id=trade_id, instrument=instrument, direction=direction,
            entry_price=entry_price, units=units,
            original_sl=sl, original_tp=tp, current_sl=sl, current_tp=tp,
            open_time=datetime.utcnow(), atr_at_entry=atr, regime_at_entry=regime,
            peak_price=entry_price,
            slippage=abs(entry_price - requested_price) if requested_price > 0 else 0.0,
        )
        self.managed_orders[trade_id] = order
        self._notify("REGISTERED", order)
        self.save_state()
        return order

    def update_price(self, trade_id: str, current_price: float) -> None:
        order = self.managed_orders.get(trade_id)
        if not order:
            return
        risk = abs(order.entry_price - order.original_sl)
        if risk <= 0:
            return

        if order.direction == "LONG":
            current_r = (current_price - order.entry_price) / risk
            if current_price > order.peak_price:
                order.peak_price = current_price
        else:
            current_r = (order.entry_price - current_price) / risk
            if current_price < order.peak_price or order.peak_price == order.entry_price:
                order.peak_price = current_price

        # Break-even
        be_cfg = self.config.get("break_even", {})
        if be_cfg.get("enabled") and not order.break_even_set and current_r >= be_cfg.get("trigger_r", 1.0):
            offset = be_cfg.get("offset_pips", 2) * 0.01
            new_sl = order.entry_price + offset if order.direction == "LONG" else order.entry_price - offset
            if self._modify_sl(trade_id, new_sl):
                order.current_sl = new_sl
                order.break_even_set = True
                self._notify("BREAK_EVEN", order, {"new_sl": new_sl})

        # Partial close
        pc_cfg = self.config.get("partial_close", {})
        if pc_cfg.get("enabled") and not order.partial_closed and current_r >= pc_cfg.get("trigger_r", 1.0):
            units_to_close = round(order.units * pc_cfg.get("close_pct", 50) / 100)
            if units_to_close > 0 and self._partial_close(trade_id, units_to_close):
                order.partial_closed = True
                order.units -= units_to_close
                self._notify("PARTIAL_CLOSE", order, {"closed_units": units_to_close})

        # Trailing stop
        ts_cfg = self.config.get("trailing_stop", {})
        if ts_cfg.get("enabled") and current_r >= ts_cfg.get("activation_r", 1.5):
            trail_distance = ts_cfg.get("trail_distance_r", 1.0) * risk
            if order.direction == "LONG":
                new_sl = order.peak_price - trail_distance
                if new_sl > order.current_sl and self._modify_sl(trade_id, new_sl):
                    order.current_sl = new_sl
                    order.trailing_active = True
            else:
                new_sl = order.peak_price + trail_distance
                if new_sl < order.current_sl and self._modify_sl(trade_id, new_sl):
                    order.current_sl = new_sl
                    order.trailing_active = True

    def _modify_sl(self, trade_id: str, new_sl: float) -> bool:
        if self.broker:
            return self.broker.modify_trade(trade_id, sl=new_sl)
        return True

    def _partial_close(self, trade_id: str, units: float) -> bool:
        if self.broker:
            return self.broker.close_trade(trade_id, units=units)
        return True

    def unregister_trade(self, trade_id: str, reason: str = "closed") -> Optional[ManagedOrder]:
        order = self.managed_orders.pop(trade_id, None)
        if order:
            self._notify("UNREGISTERED", order, {"reason": reason})
            self.save_state()
        return order

    def save_state(self) -> None:
        state = {}
        for tid, o in self.managed_orders.items():
            state[tid] = {
                "trade_id": o.trade_id, "instrument": o.instrument, "direction": o.direction,
                "entry_price": o.entry_price, "units": o.units,
                "original_sl": o.original_sl, "original_tp": o.original_tp,
                "current_sl": o.current_sl, "current_tp": o.current_tp,
                "open_time": o.open_time.isoformat(), "atr_at_entry": o.atr_at_entry,
                "regime_at_entry": o.regime_at_entry, "partial_closed": o.partial_closed,
                "break_even_set": o.break_even_set, "trailing_active": o.trailing_active,
                "peak_price": o.peak_price,
            }
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(json.dumps(state, indent=2, default=str), encoding="utf-8")

    def load_state(self) -> int:
        if not STATE_FILE.exists():
            return 0
        try:
            state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            for tid, data in state.items():
                self.managed_orders[tid] = ManagedOrder(
                    trade_id=data["trade_id"], instrument=data["instrument"], direction=data["direction"],
                    entry_price=data["entry_price"], units=data["units"],
                    original_sl=data["original_sl"], original_tp=data["original_tp"],
                    current_sl=data["current_sl"], current_tp=data["current_tp"],
                    open_time=datetime.fromisoformat(data["open_time"]),
                    atr_at_entry=data.get("atr_at_entry", 0), regime_at_entry=data.get("regime_at_entry", ""),
                    partial_closed=data.get("partial_closed", False), break_even_set=data.get("break_even_set", False),
                    trailing_active=data.get("trailing_active", False), peak_price=data.get("peak_price", data["entry_price"]),
                )
            return len(self.managed_orders)
        except Exception as e:
            logger.error("Failed to load state: %s", e)
            return 0
