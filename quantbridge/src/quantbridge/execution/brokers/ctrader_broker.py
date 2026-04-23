from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Optional, Any

from quantbridge.execution.broker_contract import BrokerContract
from quantbridge.execution.clients.ctrader_mock_client import CTraderMockClient
from quantbridge.execution.clients.ctrader_openapi_client import CTraderOpenApiClient
from quantbridge.execution.health import HealthReport
from quantbridge.execution.models import AccountState, OrderResult, Position
from quantbridge.execution.symbol_registry import map_symbol, normalize_units


class CTraderBroker(BrokerContract):
    def __init__(
        self,
        account_id: str,
        access_token: str,
        client_id: str = "",
        client_secret: str = "",
        instrument: str = "XAUUSD",
        environment: str = "demo",
        mode: str = "mock",
        initial_balance: float = 10000.0,
        mock_price: float = 2500.0,
        mock_spread: float = 0.2,
    ) -> None:
        self.account_id = account_id
        self.access_token = access_token
        self.client_id = client_id
        self.client_secret = client_secret
        self.instrument = instrument
        self.environment = environment
        self.mode = mode
        self._last_error: Optional[str] = None
        self._last_success_at: Optional[datetime] = None

        if mode == "openapi":
            self.client = CTraderOpenApiClient(
                account_id=account_id,
                access_token=access_token,
                environment=environment,
                client_id=client_id,
                client_secret=client_secret,
            )
        else:
            self.client = CTraderMockClient(
                account_id=account_id or "icmarkets-demo-001",
                instrument=instrument,
                initial_balance=initial_balance,
                mock_price=mock_price,
                mock_spread=mock_spread,
            )

    @property
    def is_connected(self) -> bool:
        return bool(getattr(self.client, "connected", False))

    def connect(self) -> bool:
        ok = self.client.connect()
        if ok:
            self._last_success_at = datetime.now(timezone.utc)
            self._last_error = None
            return True
        self._last_error = getattr(self.client, "last_error", "connect_failed")
        return False

    def disconnect(self) -> None:
        self.client.disconnect()

    def health_check(self) -> HealthReport:
        if self.is_connected and self._last_error is None:
            return HealthReport(
                status="healthy",
                session_state="connected",
                last_success_at=self._last_success_at,
            )
        if self.is_connected and self._last_error:
            return HealthReport(
                status="degraded",
                session_state="connected",
                last_error=self._last_error,
                last_success_at=self._last_success_at,
            )
        return HealthReport(
            status="unhealthy",
            session_state="disconnected",
            last_error=self._last_error or "not_connected",
            last_success_at=self._last_success_at,
        )

    def get_current_price(self, instrument: Optional[str] = None) -> Optional[Dict[str, float]]:
        broker_symbol = map_symbol("ctrader", instrument or self.instrument)
        px = self.client.get_current_price(broker_symbol)
        if px:
            self._last_success_at = datetime.now(timezone.utc)
            self._last_error = None
        else:
            self._last_error = "price_unavailable"
        return px

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
        internal_symbol = instrument or self.instrument
        broker_symbol = map_symbol("ctrader", internal_symbol)
        normalized_units = normalize_units("ctrader", internal_symbol, units)
        result = self.client.submit_market_order(
            instrument=broker_symbol,
            direction=direction,
            units=normalized_units,
            sl=sl,
            tp=tp,
            comment=comment,
            client_order_ref=client_order_ref,
        )
        if result.success:
            self._last_success_at = datetime.now(timezone.utc)
            self._last_error = None
        else:
            self._last_error = result.message or result.error_code or "order_rejected"
        return result

    def modify_trade(self, trade_id: str, sl: Optional[float] = None, tp: Optional[float] = None) -> bool:
        ok = self.client.modify_trade(trade_id, sl=sl, tp=tp)
        if ok:
            self._last_success_at = datetime.now(timezone.utc)
            self._last_error = None
        else:
            self._last_error = "modify_failed"
        return ok

    def close_trade(self, trade_id: str, units: Optional[float] = None) -> bool:
        ok = self.client.close_trade(trade_id, units=units)
        if ok:
            self._last_success_at = datetime.now(timezone.utc)
            self._last_error = None
        else:
            self._last_error = "close_failed"
        return ok

    def get_open_trades(self, instrument: Optional[str] = None) -> List[Position]:
        broker_symbol = map_symbol("ctrader", instrument or self.instrument)
        trades = self.client.get_open_trades(broker_symbol)
        self._last_success_at = datetime.now(timezone.utc)
        self._last_error = None
        return trades

    def get_account_state(self) -> Optional[AccountState]:
        state = self.client.get_account_state()
        if state:
            self._last_success_at = datetime.now(timezone.utc)
            self._last_error = None
        else:
            self._last_error = "account_state_unavailable"
        return state

    def sync_positions(self, instrument: Optional[str] = None) -> List[Position]:
        return self.get_open_trades(instrument=instrument)

    def fetch_ohlcv(
        self,
        instrument: Optional[str],
        timeframe: str,
        start: datetime,
        end: datetime,
    ) -> List[Dict[str, Any]]:
        broker_symbol = map_symbol("ctrader", instrument or self.instrument)
        if not hasattr(self.client, "fetch_ohlcv"):
            return []
        rows = self.client.fetch_ohlcv(
            instrument=broker_symbol,
            timeframe=timeframe,
            start=start,
            end=end,
        )
        if rows:
            self._last_success_at = datetime.now(timezone.utc)
            self._last_error = None
        else:
            self._last_error = getattr(self.client, "last_error", "trendbars_unavailable")
        return rows

    # Compatibility aliases used by QuantBuild adapter probing.
    def get_ohlcv(self, instrument: Optional[str], timeframe: str, start: datetime, end: datetime):
        return self.fetch_ohlcv(instrument=instrument, timeframe=timeframe, start=start, end=end)

    def get_candles(self, instrument: Optional[str], timeframe: str, start: datetime, end: datetime):
        return self.fetch_ohlcv(instrument=instrument, timeframe=timeframe, start=start, end=end)

    def get_trendbars(self, instrument: Optional[str], timeframe: str, start: datetime, end: datetime):
        return self.fetch_ohlcv(instrument=instrument, timeframe=timeframe, start=start, end=end)
