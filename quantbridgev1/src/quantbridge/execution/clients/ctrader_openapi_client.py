from __future__ import annotations

import logging
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from quantbridge.execution.errors import classify_error
from quantbridge.execution.models import AccountState, OrderResult, Position

logger = logging.getLogger(__name__)


def _from_money(value: int, digits: int = 2) -> float:
    try:
        return float(value) / (10 ** int(digits))
    except Exception:
        return float(value)


def _from_price(value: int) -> float:
    # cTrader commonly represents prices in 1/100000 precision.
    try:
        v = float(value)
    except Exception:
        return 0.0
    if abs(v) >= 100000:
        return v / 100000.0
    return v


class CTraderOpenApiClient:
    """Real cTrader Open API transport client.

    Uses OpenApiPy (ctrader-open-api) and runs Twisted reactor in a background thread.
    """

    def __init__(
        self,
        account_id: str,
        access_token: str,
        environment: str = "demo",
        client_id: str = "",
        client_secret: str = "",
        request_timeout_seconds: float = 8.0,
    ) -> None:
        self.account_id = account_id
        self.access_token = access_token
        self.environment = environment
        self.client_id = client_id
        self.client_secret = client_secret
        self.request_timeout_seconds = float(request_timeout_seconds)
        self.connected = False
        self.last_error: Optional[str] = None
        self.last_success_at: Optional[datetime] = None

        self._client = None
        self._reactor = None
        self._reactor_thread: Optional[threading.Thread] = None
        self._reactor_started = threading.Event()
        self._spot_by_symbol_id: Dict[int, Dict[str, float]] = {}
        self._symbol_id_by_name: Dict[str, int] = {}
        self._symbol_name_by_id: Dict[int, str] = {}
        self._symbol_digits_by_id: Dict[int, int] = {}
        self._money_digits: int = 2

    def _set_success(self) -> None:
        self.last_error = None
        self.last_success_at = datetime.now(timezone.utc)

    def _set_error(self, message: str) -> None:
        self.last_error = message

    def _ensure_reactor(self) -> bool:
        try:
            from twisted.internet import reactor  # type: ignore
        except Exception as e:
            self._set_error(f"reactor_init_failed: {e}")
            return False

        self._reactor = reactor
        if reactor.running:
            self._reactor_started.set()
            return True

        def _run_reactor() -> None:
            try:
                reactor.run(installSignalHandlers=False)
            except Exception as e:  # pragma: no cover
                self._set_error(f"reactor_runtime_failed: {e}")

        self._reactor_thread = threading.Thread(target=_run_reactor, daemon=True, name="ctrader-reactor")
        self._reactor_thread.start()
        time.sleep(0.15)
        self._reactor_started.set()
        return True

    def _to_blocking(self, deferred, timeout: Optional[float] = None):
        done = threading.Event()
        result_box = {"value": None, "error": None}

        def _ok(value):
            result_box["value"] = value
            done.set()
            return None

        def _err(failure):
            result_box["error"] = failure
            done.set()
            # Consume Twisted failure so it doesn't bubble as unhandled.
            return None

        deferred.addCallbacks(_ok, _err)
        if not done.wait(timeout or self.request_timeout_seconds):
            raise TimeoutError("openapi_request_timeout")
        if result_box["error"] is not None:
            raise RuntimeError(str(result_box["error"]))
        return result_box["value"]

    def _send_message(self, message):
        if self._client is None:
            raise RuntimeError("client_not_initialized")
        request_id = f"qb-{uuid.uuid4().hex[:12]}"
        logger.info(
            "ctrader.request action=send request_id=%s payload=%s account=%s",
            request_id,
            type(message).__name__,
            self.account_id,
        )
        from twisted.internet.threads import blockingCallFromThread

        def _send_and_wait():
            return self._client.send(
                message,
                clientMsgId=request_id,
                responseTimeoutInSeconds=self.request_timeout_seconds,
            )

        response = blockingCallFromThread(self._reactor, _send_and_wait)
        response = self._extract_payload(response)
        logger.info(
            "ctrader.response action=recv request_id=%s payload=%s",
            request_id,
            type(response).__name__,
        )
        return response

    def _extract_payload(self, message):
        # OpenApiPy may return a ProtoMessage wrapper; normalize to typed payload.
        try:
            payload_type = getattr(message, "payloadType", None)
            payload = getattr(message, "payload", None)
            if payload_type is not None and payload is not None:
                from ctrader_open_api import Protobuf

                extracted = Protobuf.extract(message)
                if extracted is not None:
                    return extracted
        except Exception:
            pass
        return message

    def _on_message(self, *args) -> None:
        # SDK callback signature differs by version:
        # - callback(message)
        # - callback(client, message)
        # Normalize both to the payload message object.
        if not args:
            return
        message = self._extract_payload(args[-1])
        # Spot updates come asynchronously as events.
        payload_name = type(message).__name__
        if payload_name != "ProtoOASpotEvent":
            return
        symbol_id = int(getattr(message, "symbolId", 0))
        if symbol_id <= 0:
            return
        bid = _from_price(getattr(message, "bid", 0))
        ask = _from_price(getattr(message, "ask", 0))
        self._spot_by_symbol_id[symbol_id] = {
            "bid": bid,
            "ask": ask,
            "spread": ask - bid,
            "time": datetime.now(timezone.utc).isoformat(),
        }

    def connect(self) -> bool:
        try:
            from ctrader_open_api import Client, EndPoints, TcpProtocol
            from ctrader_open_api.messages.OpenApiMessages_pb2 import (
                ProtoOAAccountAuthReq,
                ProtoOAApplicationAuthReq,
                ProtoOASymbolsListReq,
            )
        except Exception as e:
            self._set_error(f"sdk_import_failed: {e}")
            return False

        if not self.account_id or not self.access_token:
            self.last_error = "auth_failed: missing account_id or access_token"
            return False

        if not self._ensure_reactor():
            return False

        host = EndPoints.PROTOBUF_DEMO_HOST if self.environment.lower() == "demo" else EndPoints.PROTOBUF_LIVE_HOST
        try:
            from twisted.internet.threads import blockingCallFromThread

            self._client = Client(host, EndPoints.PROTOBUF_PORT, TcpProtocol)
            self._client.setMessageReceivedCallback(self._on_message)

            def _start_and_wait():
                self._client.startService()
                return self._client.whenConnected(failAfterFailures=1)

            blockingCallFromThread(
                self._reactor,
                _start_and_wait,
            )
        except Exception as e:
            self._set_error(f"session_connect_failed: {e}")
            return False

        try:
            if self.client_id and self.client_secret:
                app_auth = ProtoOAApplicationAuthReq(
                    clientId=self.client_id,
                    clientSecret=self.client_secret,
                )
                self._send_message(app_auth)

            account_auth = ProtoOAAccountAuthReq(
                ctidTraderAccountId=int(self.account_id),
                accessToken=self.access_token,
            )
            self._send_message(account_auth)

            symbols_res = self._send_message(
                ProtoOASymbolsListReq(
                    ctidTraderAccountId=int(self.account_id),
                    includeArchivedSymbols=False,
                )
            )
            self._symbol_id_by_name.clear()
            self._symbol_name_by_id.clear()
            self._symbol_digits_by_id.clear()
            for item in getattr(symbols_res, "symbol", []):
                name = str(getattr(item, "symbolName", "")).upper()
                symbol_id = int(getattr(item, "symbolId", 0))
                if name and symbol_id > 0:
                    self._symbol_id_by_name[name] = symbol_id
                    self._symbol_name_by_id[symbol_id] = name
                    digits = int(getattr(item, "digits", 5) or 5)
                    self._symbol_digits_by_id[symbol_id] = digits
        except Exception as e:
            msg = str(e)
            if "TimeoutError" in msg or "timed out" in msg or "Deferred" in msg:
                self._set_error(
                    "auth_or_bootstrap_failed: timeout (likely invalid token or missing app credentials)",
                )
            else:
                self._set_error(f"auth_or_bootstrap_failed: {e}")
            return False

        self.connected = True
        self._set_success()
        return True

    def disconnect(self) -> None:
        if self._client is not None:
            try:
                self._client.stopService()
            except Exception:
                pass
        self.connected = False

    def _resolve_symbol(self, instrument: Optional[str]) -> Tuple[str, Optional[int]]:
        name = str(instrument or "").upper()
        if not name:
            name = "XAUUSD"
        symbol_id = self._symbol_id_by_name.get(name)
        return name, symbol_id

    def _resolve_trendbar_period(self, timeframe: str):
        tf = str(timeframe or "").strip().lower()
        aliases = {
            "m1": "M1",
            "1m": "M1",
            "m5": "M5",
            "5m": "M5",
            "m15": "M15",
            "15m": "M15",
            "m30": "M30",
            "30m": "M30",
            "h1": "H1",
            "1h": "H1",
            "h4": "H4",
            "4h": "H4",
            "d1": "D1",
            "1d": "D1",
        }
        period_name = aliases.get(tf)
        if period_name is None:
            raise ValueError(f"unsupported_timeframe: {timeframe}")

        from ctrader_open_api.messages import OpenApiModelMessages_pb2 as model

        # OpenApiPy enum names typically include a PREFIX (e.g. M1), but we keep
        # a defensive fallback in case only numeric values are present.
        for attr in (
            period_name,
            f"TB_PERIOD_{period_name}",
            f"ProtoOATrendbarPeriod_{period_name}",
        ):
            if hasattr(model, attr):
                return getattr(model, attr)

        fallback_numeric = {
            "M1": 1,
            "M5": 2,
            "M15": 3,
            "M30": 4,
            "H1": 5,
            "H4": 6,
            "D1": 10,
        }
        return fallback_numeric[period_name]

    def _trendbar_to_ohlcv(
        self,
        trendbar: object,
        symbol_id: int,
        symbol_name: str,
    ) -> Optional[Dict[str, float]]:
        ts_minutes = int(getattr(trendbar, "utcTimestampInMinutes", 0) or 0)
        if ts_minutes <= 0:
            return None

        digits = int(self._symbol_digits_by_id.get(symbol_id, 5))
        price_scale = 10 ** digits

        low_raw = int(getattr(trendbar, "low", 0) or 0)
        delta_open = int(getattr(trendbar, "deltaOpen", 0) or 0)
        delta_close = int(getattr(trendbar, "deltaClose", 0) or 0)
        delta_high = int(getattr(trendbar, "deltaHigh", 0) or 0)
        volume = float(getattr(trendbar, "volume", 0) or 0)

        low = low_raw / price_scale
        open_ = (low_raw + delta_open) / price_scale
        close = (low_raw + delta_close) / price_scale
        high = (low_raw + delta_high) / price_scale
        ts = datetime.fromtimestamp(ts_minutes * 60, tz=timezone.utc)

        return {
            "timestamp": ts.isoformat(),
            "symbol": symbol_name,
            "open": float(open_),
            "high": float(high),
            "low": float(low),
            "close": float(close),
            "volume": float(volume),
        }

    def _subscribe_spot(self, symbol_id: int) -> bool:
        try:
            from ctrader_open_api.messages.OpenApiMessages_pb2 import ProtoOASubscribeSpotsReq

            self._send_message(
                ProtoOASubscribeSpotsReq(
                    ctidTraderAccountId=int(self.account_id),
                    symbolId=[int(symbol_id)],
                    subscribeToSpotTimestamp=True,
                )
            )
            return True
        except Exception as e:
            self._set_error(f"spot_subscribe_failed: {e}")
            return False

    def get_current_price(self, instrument: Optional[str] = None) -> Optional[Dict[str, float]]:
        if not self.connected:
            self._set_error("session_expired: not connected")
            return None
        symbol_name, symbol_id = self._resolve_symbol(instrument)
        if symbol_id is None:
            self._set_error(f"invalid_symbol: {symbol_name}")
            return None
        if symbol_id not in self._spot_by_symbol_id:
            if not self._subscribe_spot(symbol_id):
                return None
            # Wait briefly for async spot event.
            for _ in range(10):
                if symbol_id in self._spot_by_symbol_id:
                    break
                time.sleep(0.25)
        spot = self._spot_by_symbol_id.get(symbol_id)
        if spot is None:
            self._set_error("price_unavailable")
            return None
        self._set_success()
        return {**spot, "instrument": symbol_name}

    def get_account_state(self) -> Optional[AccountState]:
        if not self.connected:
            self._set_error("session_expired: not connected")
            return None
        try:
            from ctrader_open_api.messages.OpenApiMessages_pb2 import ProtoOATraderReq

            res = self._send_message(
                ProtoOATraderReq(ctidTraderAccountId=int(self.account_id))
            )
            trader = getattr(res, "trader", None)
            if trader is None:
                self._set_error("account_state_unavailable")
                return None
            self._money_digits = int(getattr(trader, "moneyDigits", self._money_digits) or self._money_digits)
            balance = _from_money(getattr(trader, "balance", 0), self._money_digits)
            self._set_success()
            return AccountState(
                account_id=str(self.account_id),
                balance=balance,
                equity=balance,
                unrealized_pnl=0.0,
                margin_used=0.0,
                margin_available=balance,
                open_trade_count=len(self.get_open_trades()),
                currency="USD",
            )
        except Exception as e:
            self._set_error(f"account_state_failed: {e}")
            return None

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
            message = "session_expired: not connected"
            return OrderResult(success=False, message=message, error_code=classify_error(message))
        try:
            from ctrader_open_api.messages import OpenApiModelMessages_pb2 as model
            from ctrader_open_api.messages.OpenApiMessages_pb2 import ProtoOANewOrderReq

            symbol_name, symbol_id = self._resolve_symbol(instrument)
            if symbol_id is None:
                message = f"invalid_symbol: {symbol_name}"
                return OrderResult(success=False, message=message, error_code=classify_error(message))

            trade_side = model.BUY if direction.upper() == "BUY" else model.SELL
            req = ProtoOANewOrderReq(
                ctidTraderAccountId=int(self.account_id),
                symbolId=int(symbol_id),
                orderType=model.MARKET,
                tradeSide=trade_side,
                volume=int(units),
                comment=comment,
                clientOrderId=client_order_ref or f"qb-{uuid.uuid4().hex[:10]}",
            )
            if sl is not None:
                req.stopLoss = float(sl)
            if tp is not None:
                req.takeProfit = float(tp)

            res = self._send_message(req)
            trade_id = ""
            fill_price = 0.0
            position = getattr(res, "position", None)
            if position is not None:
                trade_id = str(getattr(position, "positionId", ""))
                fill_price = _from_price(getattr(position, "price", 0))
            order = getattr(res, "order", None)
            order_id = str(getattr(order, "orderId", "")) if order is not None else trade_id

            if not trade_id and not order_id:
                message = f"order_rejected: unexpected response {type(res).__name__}"
                return OrderResult(
                    success=False,
                    message=message,
                    error_code=classify_error(message),
                    raw_response={"payload": type(res).__name__},
                )

            self._set_success()
            return OrderResult(
                success=True,
                order_id=order_id or None,
                trade_id=trade_id or None,
                fill_price=fill_price or None,
                message="order_accepted",
                raw_response={"payload": type(res).__name__},
            )
        except Exception as e:
            message = f"order_rejected: {e}"
            self._set_error(message)
            return OrderResult(
                success=False,
                message=message,
                error_code=classify_error(message),
            )

    def get_open_trades(self, instrument: Optional[str] = None) -> List[Position]:
        if not self.connected:
            self._set_error("session_expired: not connected")
            return []
        try:
            from ctrader_open_api.messages import OpenApiModelMessages_pb2 as model
            from ctrader_open_api.messages.OpenApiMessages_pb2 import ProtoOAReconcileReq

            symbol_name, symbol_id = self._resolve_symbol(instrument)
            px = self.get_current_price(symbol_name) if symbol_id is not None else None
            mid = ((px["ask"] + px["bid"]) / 2.0) if px else 0.0

            res = self._send_message(
                ProtoOAReconcileReq(ctidTraderAccountId=int(self.account_id))
            )
            out: List[Position] = []
            for p in getattr(res, "position", []):
                td = getattr(p, "tradeData", None)
                if td is None:
                    continue
                psid = int(getattr(td, "symbolId", 0))
                if symbol_id is not None and psid != symbol_id:
                    continue
                side_value = int(getattr(td, "tradeSide", 0))
                direction = "LONG" if side_value == int(model.BUY) else "SHORT"
                entry_price = _from_price(getattr(p, "price", 0))
                units = float(getattr(td, "volume", 0))
                current = mid or entry_price
                pnl_per_unit = (current - entry_price) if direction == "LONG" else (entry_price - current)
                out.append(
                    Position(
                        trade_id=str(getattr(p, "positionId", "")),
                        instrument=self._symbol_name_by_id.get(psid, symbol_name),
                        direction=direction,
                        units=units,
                        entry_price=entry_price,
                        current_price=current,
                        unrealized_pnl=pnl_per_unit * units,
                        sl=float(getattr(p, "stopLoss", 0)) or None,
                        tp=float(getattr(p, "takeProfit", 0)) or None,
                    )
                )
            self._set_success()
            return out
        except Exception as e:
            self._set_error(f"reconcile_failed: {e}")
            return []

    def close_trade(self, trade_id: str, units: Optional[float] = None) -> bool:
        if not self.connected:
            self._set_error("session_expired: not connected")
            return False
        try:
            from ctrader_open_api.messages.OpenApiMessages_pb2 import ProtoOAClosePositionReq

            req = ProtoOAClosePositionReq(
                ctidTraderAccountId=int(self.account_id),
                positionId=int(trade_id),
            )
            if units is not None:
                req.volume = int(units)
            self._send_message(req)
            self._set_success()
            return True
        except Exception as e:
            self._set_error(f"close_failed: {e}")
            return False

    def modify_trade(self, trade_id: str, sl: Optional[float] = None, tp: Optional[float] = None) -> bool:
        if not self.connected:
            self._set_error("session_expired: not connected")
            return False
        if sl is None and tp is None:
            return True
        try:
            from ctrader_open_api.messages.OpenApiMessages_pb2 import ProtoOAAmendPositionSLTPReq

            req = ProtoOAAmendPositionSLTPReq(
                ctidTraderAccountId=int(self.account_id),
                positionId=int(trade_id),
            )
            if sl is not None:
                req.stopLoss = float(sl)
            if tp is not None:
                req.takeProfit = float(tp)
            self._send_message(req)
            self._set_success()
            return True
        except Exception as e:
            self._set_error(f"modify_failed: {e}")
            return False

    def fetch_ohlcv(
        self,
        instrument: str,
        timeframe: str,
        start: datetime,
        end: datetime,
    ) -> List[Dict[str, float]]:
        if not self.connected:
            self._set_error("session_expired: not connected")
            return []

        try:
            from ctrader_open_api.messages.OpenApiMessages_pb2 import ProtoOAGetTrendbarsReq
        except Exception as e:
            self._set_error(f"trendbars_sdk_import_failed: {e}")
            return []

        symbol_name, symbol_id = self._resolve_symbol(instrument)
        if symbol_id is None:
            self._set_error(f"invalid_symbol: {symbol_name}")
            return []

        try:
            period = self._resolve_trendbar_period(timeframe)
            from_ts_ms = int(start.timestamp() * 1000)
            to_ts_ms = int(end.timestamp() * 1000)

            req = ProtoOAGetTrendbarsReq(
                ctidTraderAccountId=int(self.account_id),
                symbolId=int(symbol_id),
                period=period,
                fromTimestamp=from_ts_ms,
                toTimestamp=to_ts_ms,
            )
            res = self._send_message(req)

            rows: List[Dict[str, float]] = []
            for tb in getattr(res, "trendbar", []):
                row = self._trendbar_to_ohlcv(tb, symbol_id=symbol_id, symbol_name=symbol_name)
                if row is not None:
                    rows.append(row)

            rows.sort(key=lambda r: r["timestamp"])
            self._set_success()
            return rows
        except Exception as e:
            self._set_error(f"trendbars_fetch_failed: {e}")
            return []
