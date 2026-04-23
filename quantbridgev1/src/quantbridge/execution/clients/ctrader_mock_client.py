from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional

from quantbridge.execution.errors import classify_error
from quantbridge.execution.models import AccountState, OrderResult, Position


@dataclass
class _MockTrade:
    trade_id: str
    instrument: str
    direction: str
    units: float
    entry_price: float
    sl: Optional[float] = None
    tp: Optional[float] = None
    open_time: Optional[datetime] = None


class CTraderMockClient:
    def __init__(
        self,
        account_id: str,
        instrument: str,
        initial_balance: float = 10000.0,
        mock_price: float = 2500.0,
        mock_spread: float = 0.2,
    ) -> None:
        self.account_id = account_id
        self.instrument = instrument
        self.initial_balance = float(initial_balance)
        self.mock_price = float(mock_price)
        self.mock_spread = float(mock_spread)
        self.connected = False
        self._trades: Dict[str, _MockTrade] = {}

    def connect(self) -> bool:
        self.connected = True
        return True

    def disconnect(self) -> None:
        self.connected = False

    def get_current_price(self, instrument: Optional[str] = None) -> Optional[Dict[str, float]]:
        if not self.connected:
            return None
        ask = self.mock_price + self.mock_spread / 2.0
        bid = self.mock_price - self.mock_spread / 2.0
        return {
            "bid": bid,
            "ask": ask,
            "spread": ask - bid,
            "time": datetime.now(timezone.utc).isoformat(),
            "instrument": instrument or self.instrument,
        }

    def get_account_state(self) -> Optional[AccountState]:
        if not self.connected:
            return None
        unrealized = 0.0
        for trade in self._trades.values():
            pnl_per_unit = (
                (self.mock_price - trade.entry_price)
                if trade.direction == "LONG"
                else (trade.entry_price - self.mock_price)
            )
            unrealized += pnl_per_unit * trade.units
        equity = self.initial_balance + unrealized
        return AccountState(
            account_id=self.account_id,
            balance=self.initial_balance,
            equity=equity,
            unrealized_pnl=unrealized,
            margin_used=0.0,
            margin_available=equity,
            open_trade_count=len(self._trades),
            currency="USD",
        )

    def submit_market_order(
        self,
        instrument: Optional[str] = None,
        direction: str = "BUY",
        units: float = 1.0,
        sl: Optional[float] = None,
        tp: Optional[float] = None,
        comment: str = "",
        client_order_ref: str = "",
    ) -> OrderResult:
        if not self.connected:
            message = "Not connected"
            return OrderResult(
                success=False,
                message=message,
                error_code=classify_error(message),
            )

        symbol = instrument or self.instrument
        px = self.get_current_price(symbol)
        if px is None:
            message = "Price unavailable"
            return OrderResult(
                success=False,
                message=message,
                error_code=classify_error(message),
            )

        side = direction.upper()
        if side not in {"BUY", "SELL"}:
            message = f"Order rejected: invalid direction {direction}"
            return OrderResult(
                success=False,
                message=message,
                error_code=classify_error(message),
            )

        fill_price = px["ask"] if side == "BUY" else px["bid"]
        internal_side = "LONG" if side == "BUY" else "SHORT"
        trade_id = f"CTRD-{int(datetime.now(timezone.utc).timestamp() * 1000)}"
        self._trades[trade_id] = _MockTrade(
            trade_id=trade_id,
            instrument=symbol,
            direction=internal_side,
            units=abs(float(units)),
            entry_price=float(fill_price),
            sl=sl,
            tp=tp,
            open_time=datetime.now(timezone.utc),
        )
        return OrderResult(
            success=True,
            order_id=trade_id,
            trade_id=trade_id,
            fill_price=float(fill_price),
            message=f"mock filled {comment}".strip(),
            raw_response={"mode": "mock", "client_order_ref": client_order_ref},
        )

    def get_open_trades(self, instrument: Optional[str] = None) -> List[Position]:
        if not self.connected:
            return []
        symbol = instrument or self.instrument
        px = self.get_current_price(symbol)
        if px is None:
            return []
        mid = (px["ask"] + px["bid"]) / 2.0
        out: List[Position] = []
        for trade in self._trades.values():
            if instrument and trade.instrument != instrument:
                continue
            pnl_per_unit = (mid - trade.entry_price) if trade.direction == "LONG" else (trade.entry_price - mid)
            out.append(
                Position(
                    trade_id=trade.trade_id,
                    instrument=trade.instrument,
                    direction=trade.direction,
                    units=trade.units,
                    entry_price=trade.entry_price,
                    current_price=mid,
                    unrealized_pnl=pnl_per_unit * trade.units,
                    sl=trade.sl,
                    tp=trade.tp,
                    open_time=trade.open_time,
                )
            )
        return out

    def close_trade(self, trade_id: str, units: Optional[float] = None) -> bool:
        trade = self._trades.get(trade_id)
        if trade is None:
            return False
        if units is None or units >= trade.units:
            self._trades.pop(trade_id, None)
            return True
        close_units = abs(float(units))
        if close_units <= 0:
            return False
        trade.units = max(0.0, trade.units - close_units)
        if trade.units == 0:
            self._trades.pop(trade_id, None)
        return True

    def modify_trade(self, trade_id: str, sl: Optional[float] = None, tp: Optional[float] = None) -> bool:
        trade = self._trades.get(trade_id)
        if trade is None:
            return False
        if sl is not None:
            trade.sl = sl
        if tp is not None:
            trade.tp = tp
        return True
