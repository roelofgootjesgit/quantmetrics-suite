"""QuantBridge execution layer for broker-agnostic order flow.

MVP scope:
request -> risk -> router -> broker adapter -> result + logging
"""
from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Dict, Optional, Protocol

from src.quantbuild.execution.broker_errors import classify_broker_error
from src.quantbuild.execution.symbol_registry import map_symbol, normalize_units

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ExecutionRequest:
    symbol: str
    side: str
    entry: float
    stop_loss: float
    take_profit: float
    risk_percent: float
    account_id: str
    units: float
    comment: str = ""


@dataclass(frozen=True)
class ExecutionResult:
    status: str
    broker: str
    account_id: str
    symbol: str
    side: str
    requested_entry: float
    filled_price: float
    broker_order_id: str
    message: str
    raw_response: Optional[dict] = None


class BrokerAdapter(Protocol):
    def place_order(self, request: ExecutionRequest) -> ExecutionResult:
        ...


class BrokerExecutionClient(Protocol):
    def submit_market_order(
        self,
        instrument: Optional[str] = None,
        direction: str = "BUY",
        units: float = 1.0,
        sl: Optional[float] = None,
        tp: Optional[float] = None,
        comment: str = "",
    ):
        ...


class RiskValidator(Protocol):
    def validate(self, request: ExecutionRequest) -> None:
        ...


class Router(Protocol):
    def select_adapter(self, request: ExecutionRequest) -> BrokerAdapter:
        ...


class BasicRiskValidator:
    def __init__(self, max_risk_percent: float = 2.0) -> None:
        self.max_risk_percent = max_risk_percent

    def validate(self, request: ExecutionRequest) -> None:
        if request.side not in {"LONG", "SHORT"}:
            raise ValueError("side must be LONG or SHORT")
        if request.entry <= 0 or request.stop_loss <= 0 or request.take_profit <= 0:
            raise ValueError("entry/stop_loss/take_profit must be positive")
        if request.units <= 0:
            raise ValueError("units must be positive")
        if request.risk_percent <= 0 or request.risk_percent > self.max_risk_percent:
            raise ValueError(
                f"risk_percent must be > 0 and <= {self.max_risk_percent}",
            )
        if request.side == "LONG" and request.stop_loss >= request.entry:
            raise ValueError("LONG requires stop_loss below entry")
        if request.side == "SHORT" and request.stop_loss <= request.entry:
            raise ValueError("SHORT requires stop_loss above entry")


class OandaAdapter:
    broker_name = "oanda"

    def __init__(self, broker: BrokerExecutionClient) -> None:
        self._broker = broker

    def place_order(self, request: ExecutionRequest) -> ExecutionResult:
        instrument = map_symbol("oanda", request.symbol)
        units = normalize_units("oanda", request.symbol, request.units)
        direction = "BUY" if request.side == "LONG" else "SELL"
        result = self._broker.submit_market_order(
            instrument=instrument,
            direction=direction,
            units=units,
            sl=request.stop_loss,
            tp=request.take_profit,
            comment=request.comment,
        )
        if not result.success:
            code = classify_broker_error(result.message)
            return ExecutionResult(
                status="rejected",
                broker=self.broker_name,
                account_id=request.account_id,
                symbol=instrument,
                side=request.side,
                requested_entry=request.entry,
                filled_price=request.entry,
                broker_order_id=result.trade_id or "",
                message=f"{code}: {result.message or 'Order rejected'}",
                raw_response=result.raw_response,
            )

        return ExecutionResult(
            status="filled",
            broker=self.broker_name,
            account_id=request.account_id,
            symbol=instrument,
            side=request.side,
            requested_entry=request.entry,
            filled_price=result.fill_price or request.entry,
            broker_order_id=result.trade_id or result.order_id or "",
            message=result.message or "Order filled",
            raw_response=result.raw_response,
        )


class CTraderAdapter:
    broker_name = "ctrader"

    def __init__(self, broker: BrokerExecutionClient) -> None:
        self._broker = broker

    def place_order(self, request: ExecutionRequest) -> ExecutionResult:
        instrument = map_symbol("ctrader", request.symbol)
        units = normalize_units("ctrader", request.symbol, request.units)
        direction = "BUY" if request.side == "LONG" else "SELL"
        result = self._broker.submit_market_order(
            instrument=instrument,
            direction=direction,
            units=units,
            sl=request.stop_loss,
            tp=request.take_profit,
            comment=request.comment,
        )
        if not result.success:
            code = classify_broker_error(result.message)
            return ExecutionResult(
                status="rejected",
                broker=self.broker_name,
                account_id=request.account_id,
                symbol=instrument,
                side=request.side,
                requested_entry=request.entry,
                filled_price=request.entry,
                broker_order_id=result.trade_id or "",
                message=f"{code}: {result.message or 'Order rejected'}",
                raw_response=result.raw_response,
            )

        return ExecutionResult(
            status="filled",
            broker=self.broker_name,
            account_id=request.account_id,
            symbol=instrument,
            side=request.side,
            requested_entry=request.entry,
            filled_price=result.fill_price or request.entry,
            broker_order_id=result.trade_id or result.order_id or "",
            message=result.message or "Order filled",
            raw_response=result.raw_response,
        )


class StaticRouter:
    def __init__(self, account_adapters: Dict[str, BrokerAdapter]) -> None:
        self._account_adapters = account_adapters

    def select_adapter(self, request: ExecutionRequest) -> BrokerAdapter:
        adapter = self._account_adapters.get(request.account_id)
        if adapter is None:
            raise ValueError(f"No adapter configured for account_id={request.account_id}")
        return adapter


class JsonExecutionLogger:
    def log(self, request: ExecutionRequest, result: ExecutionResult) -> None:
        payload = {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "request": asdict(request),
            "result": asdict(result),
        }
        logger.info("quantbridge.execution=%s", json.dumps(payload))


class QuantBridgeEngine:
    def __init__(
        self,
        risk_validator: RiskValidator,
        router: Router,
        logger_: JsonExecutionLogger,
    ) -> None:
        self._risk_validator = risk_validator
        self._router = router
        self._logger = logger_

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        self._risk_validator.validate(request)
        adapter = self._router.select_adapter(request)
        result = adapter.place_order(request)
        self._logger.log(request, result)
        return result
