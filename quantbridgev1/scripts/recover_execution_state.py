from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

import yaml

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from quantbridge.execution.brokers.ctrader_broker import CTraderBroker
from quantbridge.execution.recovery import ExecutionRecoveryManager


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


def main() -> int:
    load_env_files()
    parser = argparse.ArgumentParser(description="Reconnect broker and rebuild local execution state.")
    parser.add_argument("--config", default="configs/ctrader_icmarkets_demo.yaml")
    parser.add_argument("--mode", choices=["mock", "openapi"], default=None)
    parser.add_argument("--registry-path", default="state/positions.json")
    parser.add_argument("--strategy", default="OCLW")
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--backoff-seconds", type=float, default=2.0)
    args = parser.parse_args()

    cfg = load_config(args.config)
    broker_cfg = cfg.get("broker", {}) or {}
    symbol_cfg = cfg.get("symbol", {}) or {}

    mode = str(args.mode or os.getenv("CTRADER_MODE") or broker_cfg.get("mode", "mock")).lower()
    account_id = str(os.getenv("CTRADER_ACCOUNT_ID") or broker_cfg.get("account_id", ""))
    access_token = str(os.getenv("CTRADER_ACCESS_TOKEN") or broker_cfg.get("access_token", ""))
    client_id = str(os.getenv("CTRADER_CLIENT_ID") or broker_cfg.get("client_id", ""))
    client_secret = str(os.getenv("CTRADER_CLIENT_SECRET") or broker_cfg.get("client_secret", ""))
    instrument = str(symbol_cfg.get("internal", broker_cfg.get("instrument", "XAUUSD")))

    broker = CTraderBroker(
        account_id=account_id,
        access_token=access_token,
        client_id=client_id,
        client_secret=client_secret,
        instrument=instrument,
        environment=str(broker_cfg.get("environment", "demo")),
        mode=mode,
    )
    manager = ExecutionRecoveryManager(
        broker=broker,
        registry_path=args.registry_path,
        reconnect_retries=args.retries,
        reconnect_backoff_seconds=args.backoff_seconds,
    )
    result = manager.startup_recover(instrument=instrument, strategy=args.strategy)
    print(json.dumps(result.__dict__, indent=2))
    return 0 if result.connected and result.last_error is None else 1


if __name__ == "__main__":
    raise SystemExit(main())
