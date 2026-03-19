from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Optional

from quantbridge.execution.broker_contract import BrokerContract
from quantbridge.execution.models import OrderResult, Position


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class OrderLifecycleResult:
    success: bool
    status: str
    order_id: Optional[str] = None
    trade_id: Optional[str] = None
    fill_confirmed: bool = False
    protection_confirmed: bool = False
    filled_units: Optional[float] = None
    message: str = ""
    error: Optional[str] = None
    timestamp: str = field(default_factory=_utc_now_iso)


class OrderManager:
    """Manage post-order lifecycle validation and protection checks."""

    def __init__(
        self,
        broker: BrokerContract,
        default_fill_timeout_seconds: float = 12.0,
        default_poll_interval_seconds: float = 1.0,
        protection_tolerance: float = 1e-6,
        failsafe_callback: Optional[Callable[[str], None]] = None,
    ) -> None:
        self.broker = broker
        self.default_fill_timeout_seconds = max(1.0, float(default_fill_timeout_seconds))
        self.default_poll_interval_seconds = max(0.2, float(default_poll_interval_seconds))
        self.protection_tolerance = abs(float(protection_tolerance))
        self.failsafe_callback = failsafe_callback

    def _trigger_failsafe(self, reason: str) -> None:
        if self.failsafe_callback is None:
            return
        try:
            self.failsafe_callback(reason)
        except Exception:
            pass

    def place_order(
        self,
        *,
        instrument: Optional[str] = None,
        direction: str = "BUY",
        units: float = 1.0,
        sl: Optional[float] = None,
        tp: Optional[float] = None,
        comment: str = "",
        client_order_ref: str = "",
    ) -> OrderResult:
        return self.broker.submit_market_order(
            instrument=instrument,
            direction=direction,
            units=units,
            sl=sl,
            tp=tp,
            comment=comment,
            client_order_ref=client_order_ref,
        )

    def confirm_fill(
        self,
        *,
        trade_id: Optional[str],
        instrument: Optional[str] = None,
        expected_units: Optional[float] = None,
        timeout_seconds: Optional[float] = None,
        poll_interval_seconds: Optional[float] = None,
    ) -> tuple[bool, Optional[Position], Optional[str]]:
        if not trade_id:
            return False, None, "missing_trade_id"

        timeout = timeout_seconds or self.default_fill_timeout_seconds
        interval = poll_interval_seconds or self.default_poll_interval_seconds
        deadline = time.time() + timeout

        while time.time() < deadline:
            positions = self.broker.sync_positions(instrument=instrument)
            for position in positions:
                if str(position.trade_id) != str(trade_id):
                    continue
                if expected_units is not None:
                    if abs(float(position.units) - float(expected_units)) > self.protection_tolerance:
                        return False, position, "partial_fill_detected"
                return True, position, None
            time.sleep(interval)
        return False, None, "fill_timeout"

    def ensure_protection(
        self,
        *,
        trade_id: str,
        sl: Optional[float],
        tp: Optional[float],
        instrument: Optional[str] = None,
        modify_if_missing: bool = True,
        timeout_seconds: Optional[float] = None,
        poll_interval_seconds: Optional[float] = None,
    ) -> tuple[bool, Optional[Position], Optional[str]]:
        timeout = timeout_seconds or self.default_fill_timeout_seconds
        interval = poll_interval_seconds or self.default_poll_interval_seconds
        deadline = time.time() + timeout
        amended_once = False

        while time.time() < deadline:
            positions = self.broker.sync_positions(instrument=instrument)
            target = next((p for p in positions if str(p.trade_id) == str(trade_id)), None)
            if target is None:
                return False, None, "position_not_found"

            sl_ok = (sl is None) or (
                target.sl is not None and abs(float(target.sl) - float(sl)) <= self.protection_tolerance
            )
            tp_ok = (tp is None) or (
                target.tp is not None and abs(float(target.tp) - float(tp)) <= self.protection_tolerance
            )
            if sl_ok and tp_ok:
                return True, target, None

            if modify_if_missing and not amended_once:
                self.broker.modify_trade(trade_id=trade_id, sl=sl, tp=tp)
                amended_once = True

            time.sleep(interval)

        return False, None, "protection_timeout"

    def place_and_validate(
        self,
        *,
        instrument: Optional[str] = None,
        direction: str = "BUY",
        units: float = 1.0,
        sl: Optional[float] = None,
        tp: Optional[float] = None,
        comment: str = "",
        client_order_ref: str = "",
        enforce_protection: bool = True,
    ) -> OrderLifecycleResult:
        order = self.place_order(
            instrument=instrument,
            direction=direction,
            units=units,
            sl=sl,
            tp=tp,
            comment=comment,
            client_order_ref=client_order_ref,
        )
        if not order.success:
            self._trigger_failsafe(f"order_rejected:{order.error_code or order.message or 'unknown'}")
            return OrderLifecycleResult(
                success=False,
                status="rejected",
                order_id=order.order_id,
                trade_id=order.trade_id,
                message=order.message or "order_rejected",
                error=order.error_code or "order_rejected",
            )

        fill_ok, filled_position, fill_error = self.confirm_fill(
            trade_id=order.trade_id,
            instrument=instrument,
            expected_units=units,
        )
        if not fill_ok:
            self._trigger_failsafe(f"fill_not_confirmed:{fill_error or 'unknown'}")
            return OrderLifecycleResult(
                success=False,
                status="fill_unconfirmed",
                order_id=order.order_id,
                trade_id=order.trade_id,
                fill_confirmed=False,
                message=fill_error or "fill_not_confirmed",
                error=fill_error or "fill_not_confirmed",
            )

        if not enforce_protection:
            return OrderLifecycleResult(
                success=True,
                status="filled",
                order_id=order.order_id,
                trade_id=order.trade_id,
                fill_confirmed=True,
                protection_confirmed=False,
                filled_units=filled_position.units if filled_position else None,
                message="order_filled_without_protection_check",
            )

        protection_ok, protected_position, protection_error = self.ensure_protection(
            trade_id=str(order.trade_id),
            sl=sl,
            tp=tp,
            instrument=instrument,
        )
        if not protection_ok:
            self._trigger_failsafe(f"protection_missing:{protection_error or 'unknown'}")
            return OrderLifecycleResult(
                success=False,
                status="protection_unconfirmed",
                order_id=order.order_id,
                trade_id=order.trade_id,
                fill_confirmed=True,
                protection_confirmed=False,
                filled_units=filled_position.units if filled_position else None,
                message=protection_error or "protection_not_confirmed",
                error=protection_error or "protection_not_confirmed",
            )

        return OrderLifecycleResult(
            success=True,
            status="validated",
            order_id=order.order_id,
            trade_id=order.trade_id,
            fill_confirmed=True,
            protection_confirmed=True,
            filled_units=protected_position.units if protected_position else None,
            message="order_validated",
        )
