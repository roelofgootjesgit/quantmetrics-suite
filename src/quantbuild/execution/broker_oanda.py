"""Oanda v20 Broker Client — real order execution for live trading."""
import logging
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Dict, List, Literal, Optional

logger = logging.getLogger(__name__)


@dataclass
class OrderResult:
    success: bool
    order_id: Optional[str] = None
    trade_id: Optional[str] = None
    fill_price: Optional[float] = None
    message: str = ""
    raw_response: Optional[dict] = None


@dataclass
class OandaPosition:
    trade_id: str
    instrument: str
    direction: Literal["LONG", "SHORT"]
    units: float
    entry_price: float
    current_price: float
    unrealized_pnl: float
    sl: Optional[float] = None
    tp: Optional[float] = None
    open_time: Optional[datetime] = None


@dataclass
class AccountInfo:
    account_id: str
    balance: float
    equity: float
    unrealized_pnl: float
    margin_used: float
    margin_available: float
    open_trade_count: int
    currency: str = "USD"


class OandaBroker:
    def __init__(
        self,
        account_id: Optional[str] = None,
        token: Optional[str] = None,
        environment: str = "practice",
        instrument: str = "XAU_USD",
    ):
        self.account_id = account_id or os.getenv("OANDA_ACCOUNT_ID", "")
        self.token = token or os.getenv("OANDA_TOKEN", "")
        self.environment = environment
        self.instrument = instrument
        self._client = None
        self._connected = False

    def connect(self) -> bool:
        if not self.account_id or not self.token:
            logger.error("Oanda credentials not configured")
            return False
        try:
            import oandapyV20
            self._client = oandapyV20.API(access_token=self.token, environment=self.environment)
            info = self.get_account_info()
            if info:
                self._connected = True
                logger.info("Connected to Oanda (%s): balance=%.2f %s", self.environment, info.balance, info.currency)
                return True
            return False
        except ImportError:
            logger.error("oandapyV20 not installed. Run: pip install oandapyV20")
            return False
        except Exception as e:
            logger.error("Failed to connect: %s", e)
            return False

    @property
    def is_connected(self) -> bool:
        return self._connected and self._client is not None

    def get_account_info(self) -> Optional[AccountInfo]:
        if not self._client:
            return None
        try:
            from oandapyV20.endpoints.accounts import AccountDetails
            r = AccountDetails(accountID=self.account_id)
            response = self._client.request(r)
            acct = response.get("account", {})
            return AccountInfo(
                account_id=self.account_id, balance=float(acct.get("balance", 0)),
                equity=float(acct.get("NAV", 0)), unrealized_pnl=float(acct.get("unrealizedPL", 0)),
                margin_used=float(acct.get("marginUsed", 0)), margin_available=float(acct.get("marginAvailable", 0)),
                open_trade_count=int(acct.get("openTradeCount", 0)), currency=acct.get("currency", "USD"),
            )
        except Exception as e:
            logger.error("Account info failed: %s", e)
            return None

    def get_current_price(self, instrument: Optional[str] = None) -> Optional[Dict[str, float]]:
        if not self._client:
            return None
        inst = instrument or self.instrument
        try:
            from oandapyV20.endpoints.pricing import PricingInfo
            r = PricingInfo(accountID=self.account_id, params={"instruments": inst})
            response = self._client.request(r)
            prices = response.get("prices", [])
            if prices:
                p = prices[0]
                return {
                    "bid": float(p["bids"][0]["price"]), "ask": float(p["asks"][0]["price"]),
                    "spread": float(p["asks"][0]["price"]) - float(p["bids"][0]["price"]), "time": p.get("time", ""),
                }
            return None
        except Exception as e:
            logger.error("Price fetch failed: %s", e)
            return None

    def submit_market_order(self, instrument: Optional[str] = None, direction: str = "BUY",
                            units: float = 1.0, sl: Optional[float] = None, tp: Optional[float] = None,
                            comment: str = "") -> OrderResult:
        if not self.is_connected:
            return OrderResult(success=False, message="Not connected")
        inst = instrument or self.instrument
        order_units = abs(units) if direction.upper() == "BUY" else -abs(units)
        order_data: Dict[str, Any] = {
            "order": {"type": "MARKET", "instrument": inst, "units": str(order_units), "timeInForce": "FOK"}
        }
        if sl is not None:
            order_data["order"]["stopLossOnFill"] = {"price": f"{sl:.5f}", "timeInForce": "GTC"}
        if tp is not None:
            order_data["order"]["takeProfitOnFill"] = {"price": f"{tp:.5f}", "timeInForce": "GTC"}
        if comment:
            order_data["order"]["clientExtensions"] = {"comment": comment[:128]}
        try:
            from oandapyV20.endpoints.orders import OrderCreate
            r = OrderCreate(accountID=self.account_id, data=order_data)
            response = self._client.request(r)
            fill = response.get("orderFillTransaction", {})
            if fill:
                return OrderResult(
                    success=True, order_id=fill.get("orderID"),
                    trade_id=fill.get("tradeOpened", {}).get("tradeID"),
                    fill_price=float(fill.get("price", 0)), message="Order filled", raw_response=response,
                )
            cancel = response.get("orderCancelTransaction", {})
            return OrderResult(success=False, message=f"Cancelled: {cancel.get('reason', 'Unknown')}", raw_response=response)
        except Exception as e:
            logger.error("Market order failed: %s", e)
            return OrderResult(success=False, message=str(e))

    def modify_trade(self, trade_id: str, sl: Optional[float] = None, tp: Optional[float] = None) -> bool:
        if not self.is_connected:
            return False
        data: Dict[str, Any] = {}
        if sl is not None:
            data["stopLoss"] = {"price": f"{sl:.5f}", "timeInForce": "GTC"}
        if tp is not None:
            data["takeProfit"] = {"price": f"{tp:.5f}", "timeInForce": "GTC"}
        if not data:
            return True
        try:
            from oandapyV20.endpoints.trades import TradeCRCDO
            self._client.request(TradeCRCDO(accountID=self.account_id, tradeID=trade_id, data=data))
            return True
        except Exception as e:
            logger.error("Modify trade %s failed: %s", trade_id, e)
            return False

    def close_trade(self, trade_id: str, units: Optional[float] = None) -> bool:
        if not self.is_connected:
            return False
        try:
            from oandapyV20.endpoints.trades import TradeClose
            data = {"units": str(int(units))} if units is not None else {}
            self._client.request(TradeClose(accountID=self.account_id, tradeID=trade_id, data=data))
            return True
        except Exception as e:
            logger.error("Close trade %s failed: %s", trade_id, e)
            return False

    def get_open_trades(self, instrument: Optional[str] = None) -> List[OandaPosition]:
        if not self.is_connected:
            return []
        try:
            from oandapyV20.endpoints.trades import TradesList
            params = {"instrument": instrument} if instrument else {}
            response = self._client.request(TradesList(accountID=self.account_id, params=params))
            positions = []
            for t in response.get("trades", []):
                units = float(t.get("currentUnits", 0))
                positions.append(OandaPosition(
                    trade_id=t.get("id", ""), instrument=t.get("instrument", ""),
                    direction="LONG" if units > 0 else "SHORT", units=abs(units),
                    entry_price=float(t.get("price", 0)), current_price=float(t.get("price", 0)),
                    unrealized_pnl=float(t.get("unrealizedPL", 0)),
                    sl=float(t["stopLossOrder"]["price"]) if t.get("stopLossOrder") else None,
                    tp=float(t["takeProfitOrder"]["price"]) if t.get("takeProfitOrder") else None,
                ))
            return positions
        except Exception as e:
            logger.error("Get trades failed: %s", e)
            return []

    def close_all_positions(self, instrument: Optional[str] = None) -> int:
        trades = self.get_open_trades(instrument or self.instrument)
        return sum(1 for t in trades if self.close_trade(t.trade_id))

    def stream_prices(self, callback: Callable[[Dict], None], instrument: Optional[str] = None, stop_event=None) -> None:
        if not self.is_connected:
            return
        inst = instrument or self.instrument
        try:
            from oandapyV20.endpoints.pricing import PricingStream
            r = PricingStream(accountID=self.account_id, params={"instruments": inst})
            for msg in self._client.request(r):
                if stop_event and stop_event.is_set():
                    break
                if msg.get("type") == "PRICE":
                    tick = {
                        "instrument": msg.get("instrument", inst),
                        "bid": float(msg["bids"][0]["price"]) if msg.get("bids") else 0,
                        "ask": float(msg["asks"][0]["price"]) if msg.get("asks") else 0,
                        "time": msg.get("time", ""),
                    }
                    tick["spread"] = tick["ask"] - tick["bid"]
                    callback(tick)
        except Exception as e:
            logger.error("Price stream error: %s", e)
            raise

    def disconnect(self) -> None:
        self._connected = False
        self._client = None
        logger.info("Disconnected from Oanda")
