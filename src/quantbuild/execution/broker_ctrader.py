"""cTrader broker client with mock mode for IC Markets demo workflows.

This module provides the same runtime surface used by LiveRunner:
- connect / disconnect / is_connected
- account info
- price fetch
- market order submit
- modify / close / list open trades

MVP note:
- mock_mode=True gives a fully local execution simulation.
- real network transport for cTrader Open API is intentionally deferred.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
import time
from typing import Dict, List, Optional

from src.quantbuild.execution.broker_oanda import AccountInfo, OandaPosition, OrderResult

logger = logging.getLogger(__name__)


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


class CTraderBroker:
    def __init__(
        self,
        account_id: Optional[str] = None,
        access_token: Optional[str] = None,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        environment: str = "demo",
        instrument: str = "XAUUSD",
        mock_mode: bool = True,
        initial_balance: float = 10000.0,
        mock_spread: float = 0.2,
        mock_price: float = 2500.0,
    ):
        self.account_id = account_id or os.getenv("CTRADER_ACCOUNT_ID", "")
        self.access_token = access_token or os.getenv("CTRADER_ACCESS_TOKEN", "")
        self.client_id = client_id or os.getenv("CTRADER_CLIENT_ID", "")
        self.client_secret = client_secret or os.getenv("CTRADER_CLIENT_SECRET", "")
        self.environment = environment
        self.instrument = instrument
        self.mock_mode = mock_mode
        self.initial_balance = float(initial_balance)
        self.mock_spread = float(mock_spread)
        self._mock_price = float(mock_price)
        self._connected = False
        self._trades: Dict[str, _MockTrade] = {}
        self._real_bridge = None

    def _init_real_bridge(self) -> bool:
        if self._real_bridge is not None:
            return True
        # Support overriding bridge location on VPS/local.
        candidate_roots = []
        env_path = os.getenv("QUANTBRIDGE_SRC_PATH", "").strip()
        if env_path:
            candidate_roots.append(Path(env_path))
        # Common sibling checkout: ../quantBridge-v.1/src
        candidate_roots.append(Path(__file__).resolve().parents[4] / "quantBridge-v.1" / "src")

        for candidate in candidate_roots:
            try_path = candidate.resolve()
            if not try_path.exists():
                continue
            self._hydrate_credentials_from_dotenv(try_path.parent)
            if str(try_path) not in sys.path:
                sys.path.insert(0, str(try_path))
            try:
                from quantbridge.execution.brokers.ctrader_broker import CTraderBroker as QB_CTraderBroker

                self._real_bridge = QB_CTraderBroker(
                    account_id=self.account_id,
                    access_token=self.access_token,
                    client_id=self.client_id,
                    client_secret=self.client_secret,
                    instrument=self.instrument,
                    environment=self.environment,
                    mode="openapi",
                )
                logger.info("Loaded QuantBridge cTrader adapter from %s", try_path)
                return True
            except Exception as e:
                logger.warning("Failed loading QuantBridge from %s: %s", try_path, e)
                continue
        logger.error("QuantBridge OpenAPI module not found. Set QUANTBRIDGE_SRC_PATH to quantBridge-v.1/src")
        return False

    def _hydrate_credentials_from_dotenv(self, bridge_repo_root: Path) -> None:
        try:
            from dotenv import dotenv_values
        except Exception:
            return

        merged: Dict[str, str] = {}
        # Prefer .env values over local.env to avoid stale local overrides.
        for env_name in ("local.env", ".env"):
            p = bridge_repo_root / env_name
            if not p.exists():
                continue
            values = dotenv_values(p)
            for k, v in values.items():
                if not k:
                    continue
                text = str(v).strip() if v is not None else ""
                if text:
                    merged[k] = text

        if not self.account_id:
            self.account_id = merged.get("CTRADER_ACCOUNT_ID", self.account_id)
        if (not self.access_token) or len(str(self.access_token).strip()) < 20:
            self.access_token = merged.get("CTRADER_ACCESS_TOKEN", self.access_token)
        if not self.client_id:
            self.client_id = merged.get("CTRADER_CLIENT_ID", self.client_id)
        if not self.client_secret:
            self.client_secret = merged.get("CTRADER_CLIENT_SECRET", self.client_secret)

    @property
    def is_connected(self) -> bool:
        return self._connected

    def health_check(self) -> bool:
        return self.get_account_info() is not None

    def connect(self) -> bool:
        if self.mock_mode:
            self._connected = True
            logger.info(
                "Connected to cTrader mock (%s) for account %s",
                self.environment,
                self.account_id or "demo-local",
            )
            return True

        if not self.account_id or not self.access_token:
            logger.error("cTrader credentials not configured (CTRADER_ACCOUNT_ID / CTRADER_ACCESS_TOKEN)")
            return False

        if not self._init_real_bridge():
            return False
        try:
            self._connected = bool(self._real_bridge.connect())
            if self._connected:
                logger.info("Connected to cTrader OpenAPI via QuantBridge adapter")
            else:
                logger.error("QuantBridge cTrader connect failed")
            return self._connected
        except Exception as e:
            logger.error("QuantBridge cTrader connect exception: %s", e)
            return False

    def disconnect(self) -> None:
        if not self.mock_mode and self._real_bridge is not None:
            try:
                self._real_bridge.disconnect()
            except Exception:
                pass
        self._connected = False
        logger.info("Disconnected from cTrader")

    def get_account_info(self) -> Optional[AccountInfo]:
        if not self.mock_mode:
            if not self.is_connected or self._real_bridge is None:
                return None
            state = self._real_bridge.get_account_state()
            if state is None:
                return None
            return AccountInfo(
                account_id=str(state.account_id),
                balance=float(state.balance),
                equity=float(state.equity),
                unrealized_pnl=float(state.unrealized_pnl),
                margin_used=float(state.margin_used),
                margin_available=float(state.margin_available),
                open_trade_count=int(state.open_trade_count),
                currency=str(state.currency),
            )

        if not self.is_connected:
            return None

        unrealized = 0.0
        for t in self._trades.values():
            px = self._mock_price
            pnl_per_unit = (px - t.entry_price) if t.direction == "LONG" else (t.entry_price - px)
            unrealized += pnl_per_unit * t.units

        equity = self.initial_balance + unrealized
        return AccountInfo(
            account_id=self.account_id or "ctrader-demo",
            balance=self.initial_balance,
            equity=equity,
            unrealized_pnl=unrealized,
            margin_used=0.0,
            margin_available=equity,
            open_trade_count=len(self._trades),
            currency="USD",
        )

    def get_account_state(self) -> Optional[AccountInfo]:
        return self.get_account_info()

    def get_current_price(self, instrument: Optional[str] = None) -> Optional[Dict[str, float]]:
        if not self.mock_mode:
            if not self.is_connected or self._real_bridge is None:
                return None
            symbol = instrument or self.instrument
            for _ in range(3):
                px = self._real_bridge.get_current_price(instrument=symbol)
                if px is not None and "ask" in px and "bid" in px:
                    return px
                time.sleep(0.35)
            return None

        if not self.is_connected:
            return None
        ask = self._mock_price + self.mock_spread / 2.0
        bid = self._mock_price - self.mock_spread / 2.0
        return {
            "bid": bid,
            "ask": ask,
            "spread": ask - bid,
            "time": datetime.now(timezone.utc).isoformat(),
        }

    def submit_market_order(
        self,
        instrument: Optional[str] = None,
        direction: str = "BUY",
        units: float = 1.0,
        sl: Optional[float] = None,
        tp: Optional[float] = None,
        comment: str = "",
    ) -> OrderResult:
        if not self.mock_mode:
            if not self.is_connected or self._real_bridge is None:
                return OrderResult(success=False, message="Not connected")
            # cTrader OpenAPI rejects absolute SL/TP on market orders; place first, then amend.
            result = self._real_bridge.submit_market_order(
                instrument=instrument or self.instrument,
                direction=direction,
                units=units,
                sl=None,
                tp=None,
                comment=comment,
            )
            if result.success and result.trade_id and (sl is not None or tp is not None):
                amended = self._real_bridge.modify_trade(result.trade_id, sl=sl, tp=tp)
                if not amended:
                    logger.warning("Order filled but SL/TP amend failed for trade %s", result.trade_id)
            return OrderResult(
                success=bool(result.success),
                order_id=result.order_id,
                trade_id=result.trade_id,
                fill_price=result.fill_price,
                message=result.message,
                raw_response=result.raw_response,
            )

        if not self.is_connected:
            return OrderResult(success=False, message="Not connected")

        side = direction.upper()
        if side not in {"BUY", "SELL"}:
            return OrderResult(success=False, message=f"Invalid direction: {direction}")

        symbol = instrument or self.instrument
        price = self.get_current_price(symbol)
        if not price:
            return OrderResult(success=False, message="Price unavailable")

        fill_price = price["ask"] if side == "BUY" else price["bid"]
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
            trade_id=trade_id,
            order_id=trade_id,
            fill_price=fill_price,
            message=f"cTrader mock fill ({comment[:64]})" if comment else "cTrader mock fill",
            raw_response={"provider": "ctrader", "mode": "mock"},
        )

    def modify_trade(self, trade_id: str, sl: Optional[float] = None, tp: Optional[float] = None) -> bool:
        if not self.mock_mode:
            if not self.is_connected or self._real_bridge is None:
                return False
            return bool(self._real_bridge.modify_trade(trade_id, sl=sl, tp=tp))

        if not self.is_connected:
            return False
        trade = self._trades.get(trade_id)
        if trade is None:
            return False
        if sl is not None:
            trade.sl = float(sl)
        if tp is not None:
            trade.tp = float(tp)
        return True

    def close_trade(self, trade_id: str, units: Optional[float] = None) -> bool:
        if not self.mock_mode:
            if not self.is_connected or self._real_bridge is None:
                return False
            close_units = units
            if close_units is None:
                for p in self._real_bridge.get_open_trades():
                    if str(p.trade_id) == str(trade_id):
                        close_units = float(p.units)
                        break
            return bool(self._real_bridge.close_trade(trade_id, units=close_units))

        if not self.is_connected:
            return False
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

    def get_open_trades(self, instrument: Optional[str] = None) -> List[OandaPosition]:
        if not self.mock_mode:
            if not self.is_connected or self._real_bridge is None:
                return []
            # When instrument is None we explicitly request all open trades.
            positions = self._real_bridge.get_open_trades(instrument=instrument)
            out: List[OandaPosition] = []
            for p in positions:
                out.append(
                    OandaPosition(
                        trade_id=str(p.trade_id),
                        instrument=str(p.instrument),
                        direction=str(p.direction),  # LONG/SHORT
                        units=float(p.units),
                        entry_price=float(p.entry_price),
                        current_price=float(p.current_price),
                        unrealized_pnl=float(p.unrealized_pnl),
                        sl=float(p.sl) if p.sl is not None else None,
                        tp=float(p.tp) if p.tp is not None else None,
                        open_time=p.open_time,
                    )
                )
            return out

        if not self.is_connected:
            return []
        symbol = instrument or self.instrument
        px = self.get_current_price(symbol)
        if not px:
            return []
        current_mid = (px["ask"] + px["bid"]) / 2.0

        positions: List[OandaPosition] = []
        for t in self._trades.values():
            if instrument and t.instrument != instrument:
                continue
            pnl_per_unit = (current_mid - t.entry_price) if t.direction == "LONG" else (t.entry_price - current_mid)
            positions.append(
                OandaPosition(
                    trade_id=t.trade_id,
                    instrument=t.instrument,
                    direction=t.direction,
                    units=t.units,
                    entry_price=t.entry_price,
                    current_price=current_mid,
                    unrealized_pnl=pnl_per_unit * t.units,
                    sl=t.sl,
                    tp=t.tp,
                    open_time=t.open_time,
                )
            )
        return positions

    def sync_positions(self, instrument: Optional[str] = None) -> List[OandaPosition]:
        return self.get_open_trades(instrument=instrument)

    def fetch_ohlcv(
        self,
        timeframe: str,
        start: datetime,
        end: datetime,
        instrument: Optional[str] = None,
    ):
        """Best-effort OHLCV fetch from QuantBridge, if adapter supports it.

        Returns a pandas DataFrame when available, otherwise ``None``.
        Kept intentionally permissive to support different adapter method names.
        """
        if self.mock_mode or not self.is_connected or self._real_bridge is None:
            return None

        symbol = instrument or self.instrument
        call_specs = (
            ("fetch_ohlcv", {"instrument": symbol, "timeframe": timeframe, "start": start, "end": end}),
            ("get_ohlcv", {"instrument": symbol, "timeframe": timeframe, "start": start, "end": end}),
            ("get_candles", {"instrument": symbol, "timeframe": timeframe, "start": start, "end": end}),
            ("get_trendbars", {"instrument": symbol, "timeframe": timeframe, "start": start, "end": end}),
        )
        for method_name, kwargs in call_specs:
            method = getattr(self._real_bridge, method_name, None)
            if method is None:
                continue
            try:
                return method(**kwargs)
            except TypeError:
                # Adapter signature may differ; try positional fallback.
                try:
                    return method(symbol, timeframe, start, end)
                except Exception:
                    continue
            except Exception:
                continue
        return None
