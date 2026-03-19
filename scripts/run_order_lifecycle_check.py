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
from quantbridge.execution.order_manager import OrderManager
from quantbridge.execution.runtime_control import RuntimeControlLoop, send_telegram_alert


def load_env_files() -> None:
    candidates = [ROOT / ".env", ROOT / "local.env"]
    original_env = set(os.environ.keys())
    for env_path in candidates:
        if not env_path.exists():
            continue
        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip()
            if not key or not value:
                continue
            if key in original_env:
                continue
            if env_path.name == "local.env" or key not in os.environ:
                os.environ[key] = value


def load_config(path: str) -> dict:
    cfg_path = Path(path)
    if not cfg_path.is_absolute():
        cfg_path = ROOT / cfg_path
    with open(cfg_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def build_alert_callback() -> callable:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()

    def _alert(message: str) -> None:
        print(f"[alert] {message}")
        if token and chat_id:
            send_telegram_alert(bot_token=token, chat_id=chat_id, message=message)

    return _alert


def main() -> int:
    load_env_files()
    parser = argparse.ArgumentParser(description="Run validated order lifecycle check with failsafe hooks.")
    parser.add_argument("--config", default="configs/ctrader_icmarkets_demo.yaml")
    parser.add_argument("--mode", choices=["mock", "openapi"], default=None)
    parser.add_argument("--registry-path", default="state/positions.json")
    parser.add_argument("--pause-file", default="state/trading.paused")
    parser.add_argument("--strategy", default="OCLW")
    parser.add_argument("--direction", choices=["BUY", "SELL"], default="BUY")
    parser.add_argument("--units", type=float, default=None)
    parser.add_argument("--sl", type=float, default=None)
    parser.add_argument("--tp", type=float, default=None)
    parser.add_argument("--comment", default="order_lifecycle_check")
    parser.add_argument("--close-after", action="store_true")
    args = parser.parse_args()

    cfg = load_config(args.config)
    broker_cfg = cfg.get("broker", {}) or {}
    symbol_cfg = cfg.get("symbol", {}) or {}
    execution_cfg = cfg.get("execution", {}) or {}

    mode = str(args.mode or os.getenv("CTRADER_MODE") or broker_cfg.get("mode", "mock")).lower()
    account_id = str(os.getenv("CTRADER_ACCOUNT_ID") or broker_cfg.get("account_id", ""))
    access_token = str(os.getenv("CTRADER_ACCESS_TOKEN") or broker_cfg.get("access_token", ""))
    client_id = str(os.getenv("CTRADER_CLIENT_ID") or broker_cfg.get("client_id", ""))
    client_secret = str(os.getenv("CTRADER_CLIENT_SECRET") or broker_cfg.get("client_secret", ""))
    instrument = str(symbol_cfg.get("internal", broker_cfg.get("instrument", "XAUUSD")))
    units = float(args.units if args.units is not None else execution_cfg.get("units", 1.0))

    broker = CTraderBroker(
        account_id=account_id,
        access_token=access_token,
        client_id=client_id,
        client_secret=client_secret,
        instrument=instrument,
        environment=str(broker_cfg.get("environment", "demo")),
        mode=mode,
    )
    alert_callback = build_alert_callback()
    runtime = RuntimeControlLoop(
        broker=broker,
        registry_path=args.registry_path,
        pause_file_path=args.pause_file,
        alert_callback=alert_callback,
    )
    manager = OrderManager(
        broker=broker,
        failsafe_callback=lambda reason: runtime.trigger_external_failsafe(
            reason=f"order_layer:{reason}",
            instrument=instrument,
        ),
    )

    if not broker.connect():
        print(json.dumps({"success": False, "error": "connect_failed"}))
        return 1

    result = manager.place_and_validate(
        instrument=instrument,
        direction=args.direction,
        units=units,
        sl=args.sl,
        tp=args.tp,
        comment=args.comment,
        client_order_ref=f"order-{uuid.uuid4().hex[:10]}",
        enforce_protection=(args.sl is not None or args.tp is not None),
    )
    output = result.__dict__.copy()

    if args.close_after and result.trade_id:
        output["close_after"] = broker.close_trade(result.trade_id, units=units)

    output["runtime_paused"] = runtime.paused
    output["strategy"] = args.strategy
    print(json.dumps(output, indent=2))
    return 0 if result.success else 2


if __name__ == "__main__":
    raise SystemExit(main())
