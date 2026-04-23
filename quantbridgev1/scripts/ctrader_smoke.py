from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import uuid

import yaml

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from quantbridge.execution.brokers.ctrader_broker import CTraderBroker


def load_local_env() -> None:
    env_candidates = [ROOT / ".env", ROOT / "local.env"]
    preexisting_env_keys = set(os.environ.keys())
    for env_path in env_candidates:
        if not env_path.exists():
            continue
        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip()
            if not key:
                continue
            if value == "":
                continue
            if key in preexisting_env_keys:
                continue
            # local.env is loaded after .env and can override file defaults.
            if env_path.name == "local.env" or key not in os.environ:
                os.environ[key] = value


def load_config(path: str) -> dict:
    cfg_path = Path(path)
    if not cfg_path.is_absolute():
        cfg_path = ROOT / cfg_path
    with open(cfg_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def main() -> int:
    load_local_env()
    parser = argparse.ArgumentParser(description="cTrader smoke tests")
    parser.add_argument("--config", default="configs/ctrader_icmarkets_demo.yaml")
    parser.add_argument("--mode", choices=["mock", "openapi"], default=None)
    parser.add_argument("--account-id", default=None, help="Override cTrader account id")
    parser.add_argument("--access-token", default=None, help="Override cTrader access token")
    parser.add_argument("--client-id", default=None, help="Override cTrader app client id")
    parser.add_argument("--client-secret", default=None, help="Override cTrader app client secret")
    args = parser.parse_args()

    cfg = load_config(args.config)
    broker_cfg = cfg.get("broker", {}) or {}
    symbol_cfg = cfg.get("symbol", {}) or {}
    execution_cfg = cfg.get("execution", {}) or {}

    effective_mode = str(
        args.mode
        or os.getenv("CTRADER_MODE")
        or broker_cfg.get("mode", "mock")
    ).lower()
    account_id = str(
        args.account_id
        or os.getenv("CTRADER_ACCOUNT_ID")
        or broker_cfg.get("account_id", "")
    )
    access_token = str(
        args.access_token
        or os.getenv("CTRADER_ACCESS_TOKEN")
        or broker_cfg.get("access_token", "")
    )
    client_id = str(
        args.client_id
        or os.getenv("CTRADER_CLIENT_ID")
        or broker_cfg.get("client_id", "")
    )
    client_secret = str(
        args.client_secret
        or os.getenv("CTRADER_CLIENT_SECRET")
        or broker_cfg.get("client_secret", "")
    )

    broker = CTraderBroker(
        account_id=account_id,
        access_token=access_token,
        client_id=client_id,
        client_secret=client_secret,
        instrument=str(symbol_cfg.get("internal", broker_cfg.get("instrument", "XAUUSD"))),
        environment=str(broker_cfg.get("environment", "demo")),
        mode=effective_mode,
    )

    report = {
        "mode": effective_mode,
        "connect": False,
        "health": False,
        "price": False,
        "place_order": False,
        "sync_positions": False,
        "close_order": False,
        "last_error": None,
    }

    if not broker.connect():
        report["last_error"] = getattr(broker.client, "last_error", "connect_failed")
        print(json.dumps(report, indent=2))
        return 1
    report["connect"] = True

    health = broker.health_check()
    report["health"] = health.status in {"healthy", "degraded"}

    px = broker.get_current_price()
    if not px:
        report["last_error"] = getattr(broker.client, "last_error", "price_unavailable")
        print(json.dumps(report, indent=2))
        return 2
    report["price"] = True

    ask = float(px["ask"])
    sl = None
    tp = None
    if effective_mode == "mock":
        sl = ask - float(execution_cfg.get("stop_loss_distance", 5.0))
        tp = ask + float(execution_cfg.get("take_profit_distance", 10.0))

    order = broker.submit_market_order(
        direction="BUY",
        units=float(execution_cfg.get("units", 1.0)),
        sl=sl,
        tp=tp,
        comment="ctrader_smoke",
        client_order_ref=f"smoke-{uuid.uuid4().hex[:10]}",
    )
    if not order.success or not order.trade_id:
        report["last_error"] = order.error_code or order.message
        print(json.dumps(report, indent=2))
        return 3
    report["place_order"] = True

    synced = broker.sync_positions()
    report["sync_positions"] = any(p.trade_id == order.trade_id for p in synced)

    report["close_order"] = broker.close_trade(
        order.trade_id,
        units=float(execution_cfg.get("units", 1.0)),
    )
    print(json.dumps(report, indent=2))
    checks = [report["connect"], report["health"], report["price"], report["place_order"], report["sync_positions"], report["close_order"]]
    return 0 if all(checks) else 4


if __name__ == "__main__":
    raise SystemExit(main())
