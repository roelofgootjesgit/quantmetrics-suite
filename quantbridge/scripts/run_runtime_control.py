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
from quantbridge.execution.runtime_control import RuntimeControlLoop, send_telegram_alert
from quantbridge.accounts.account_state_machine import AccountStateMachine
from quantbridge.ops.observability import JsonlEventSink


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
    parser = argparse.ArgumentParser(description="Run runtime reconciliation and failsafe control loop.")
    parser.add_argument("--config", default="configs/ctrader_icmarkets_demo.yaml")
    parser.add_argument("--mode", choices=["mock", "openapi"], default=None)
    parser.add_argument("--registry-path", default="state/positions.json")
    parser.add_argument("--pause-file", default="state/trading.paused")
    parser.add_argument("--account-state-file", default="state/account_states.json")
    parser.add_argument("--events-file", default="")
    parser.add_argument("--account-status", choices=["demo", "challenge", "funded", "paused", "breached", "disabled"], default=None)
    parser.add_argument("--strategy", default="OCLW")
    parser.add_argument("--poll-seconds", type=float, default=5.0)
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--backoff-seconds", type=float, default=2.0)
    parser.add_argument("--failsafe-streak", type=int, default=3)
    parser.add_argument("--no-close-on-failsafe", action="store_true")
    parser.add_argument("--max-iterations", type=int, default=None)
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
    account_machine = AccountStateMachine(path=args.account_state_file)
    event_sink = JsonlEventSink(path=args.events_file, source="runtime") if args.events_file else None
    if args.account_status is not None:
        account_machine.set_state(
            account_id=account_id,
            status=args.account_status,  # type: ignore[arg-type]
            reason="runtime_cli_override",
        )
    runtime = RuntimeControlLoop(
        broker=broker,
        registry_path=args.registry_path,
        pause_file_path=args.pause_file,
        account_id=account_id,
        account_state_machine=account_machine,
        poll_interval_seconds=args.poll_seconds,
        reconnect_retries=args.retries,
        reconnect_backoff_seconds=args.backoff_seconds,
        mismatch_streak_failsafe=args.failsafe_streak,
        close_on_failsafe=not args.no_close_on_failsafe,
        alert_callback=build_alert_callback(),
        event_callback=(event_sink.emit if event_sink else None),
    )

    history = runtime.run_forever(
        instrument=instrument,
        strategy=args.strategy,
        max_iterations=args.max_iterations,
    )
    output = [step.__dict__ for step in history]
    print(json.dumps(output, indent=2))

    if not output:
        return 1
    final = output[-1]
    if final.get("paused"):
        return 2
    if final.get("last_error"):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
