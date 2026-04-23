#!/usr/bin/env python3
"""Isolate cTrader Open API connectivity: env shape, TCP, connect + QuantBridge last_error.

Run from quantbuild root with the same environment as live (orchestrator .env), e.g.:

  cd /root/dev/quant/quantbuild
  set -a && source ../quantmetrics_os/orchestrator/.env && set +a   # QuantOS
  .venv/bin/python scripts/diagnose_ctrader_connect.py -c configs/demo_loose_ctrader.yaml

Does not print full access tokens.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import socket
import sys
from pathlib import Path

logging.getLogger("src.quantbuild.execution.broker_ctrader").setLevel(logging.CRITICAL)

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.quantbuild.config import load_config
from src.quantbuild.execution.broker_factory import create_broker


def _token_meta(raw: str) -> dict:
    s = (raw or "").strip()
    if not s:
        return {"present": False, "len": 0, "tail": ""}
    tail = s[-4:] if len(s) > 4 else ""
    return {"present": True, "len": len(s), "tail": tail}


def _tcp_probe(host: str, port: int, timeout: float = 5.0) -> dict:
    try:
        with socket.create_connection((host, int(port)), timeout=timeout):
            return {"ok": True, "error": None}
    except OSError as e:
        return {"ok": False, "error": str(e)}


def _sdk_import_probe() -> dict:
    out: dict = {"twisted": None, "ctrader_open_api": None, "endpoints": None}
    try:
        import twisted  # noqa: F401

        out["twisted"] = "ok"
    except Exception as e:
        out["twisted"] = f"fail: {e}"
    try:
        from ctrader_open_api import EndPoints  # type: ignore

        out["ctrader_open_api"] = "ok"
        out["endpoints"] = {
            "demo_host": EndPoints.PROTOBUF_DEMO_HOST,
            "live_host": EndPoints.PROTOBUF_LIVE_HOST,
            "port": int(EndPoints.PROTOBUF_PORT),
        }
    except Exception as e:
        out["ctrader_open_api"] = f"fail: {e}"
    return out


def _connect_detail(broker) -> dict:
    """broker: QuantBuild CTraderBroker after connect() attempt."""
    rb = getattr(broker, "_real_bridge", None)
    detail: dict = {"quantbridge_last_error": None, "client_last_error": None}
    if rb is None:
        return detail
    detail["quantbridge_last_error"] = getattr(rb, "_last_error", None)
    client = getattr(rb, "client", None)
    if client is not None:
        detail["client_last_error"] = getattr(client, "last_error", None)
    return detail


def main() -> int:
    parser = argparse.ArgumentParser(description="Diagnose cTrader Open API connect")
    parser.add_argument("-c", "--config", default="configs/demo_loose_ctrader.yaml")
    args = parser.parse_args()

    cfg_path = ROOT / args.config if not Path(args.config).is_absolute() else Path(args.config)
    cfg = load_config(str(cfg_path))
    broker_cfg = cfg.get("broker") or {}

    env_bridge = os.getenv("QUANTBRIDGE_SRC_PATH", "").strip()
    report: dict = {
        "config": str(cfg_path),
        "broker_environment": str(broker_cfg.get("environment", "demo")),
        "mock_mode_yaml": bool(broker_cfg.get("mock_mode", True)),
        "QUANTBRIDGE_SRC_PATH": env_bridge or "(unset)",
        "CTRADER_ACCOUNT_ID_env": _token_meta(os.getenv("CTRADER_ACCOUNT_ID", "")),
        "CTRADER_ACCESS_TOKEN_env": _token_meta(os.getenv("CTRADER_ACCESS_TOKEN", "")),
        "sdk": _sdk_import_probe(),
    }

    ep = report["sdk"].get("endpoints") or {}
    if ep.get("demo_host") and ep.get("port"):
        demo = ep["demo_host"]
        port = int(ep["port"])
        report["tcp_demo_openapi"] = _tcp_probe(demo, port)
    else:
        report["tcp_demo_openapi"] = {"ok": None, "error": "skipped_no_endpoints"}

    broker = create_broker(cfg)
    report["resolved_mock_mode"] = bool(getattr(broker, "mock_mode", True))
    report["resolved_account_id"] = str(getattr(broker, "account_id", "") or "")
    report["resolved_account_id_is_digit"] = report["resolved_account_id"].isdigit()
    report["resolved_access_token"] = _token_meta(str(getattr(broker, "access_token", "") or ""))

    if report["resolved_mock_mode"]:
        report["connect_skipped"] = "mock_mode True — set broker.mock_mode false in YAML for real probe"
        print(json.dumps(report, indent=2))
        return 0

    ok = bool(broker.connect())
    report["connect_ok"] = ok
    if not ok:
        report["failure_detail"] = _connect_detail(broker)
    try:
        broker.disconnect()
    except Exception:
        pass

    print(json.dumps(report, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
