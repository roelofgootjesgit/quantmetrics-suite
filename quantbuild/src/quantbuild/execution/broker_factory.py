"""Broker factory for selecting execution provider from config."""
from __future__ import annotations

from typing import Any, Dict

from src.quantbuild.execution.broker_ctrader import CTraderBroker
from src.quantbuild.execution.broker_contract import BrokerContract
from src.quantbuild.execution.broker_oanda import OandaBroker


def create_broker(cfg: Dict[str, Any]) -> BrokerContract:
    broker_cfg = cfg.get("broker", {}) or {}
    provider = str(broker_cfg.get("provider", "ctrader")).lower()

    if provider == "ctrader":
        return CTraderBroker(
            account_id=broker_cfg.get("account_id", ""),
            access_token=broker_cfg.get("access_token", ""),
            client_id=broker_cfg.get("client_id", ""),
            client_secret=broker_cfg.get("client_secret", ""),
            environment=broker_cfg.get("environment", "demo"),
            instrument=broker_cfg.get("instrument", cfg.get("symbol", "XAUUSD")),
            mock_mode=bool(broker_cfg.get("mock_mode", True)),
            initial_balance=float(broker_cfg.get("initial_balance", 10000)),
            mock_spread=float(broker_cfg.get("mock_spread", 0.2)),
            mock_price=float(broker_cfg.get("mock_price", 2500.0)),
        )

    if provider == "oanda":
        return OandaBroker(
            account_id=broker_cfg.get("account_id", ""),
            token=broker_cfg.get("token", ""),
            environment=broker_cfg.get("environment", "practice"),
            instrument=broker_cfg.get("instrument", "XAU_USD"),
        )

    raise ValueError(f"Unsupported broker provider: {provider}")
