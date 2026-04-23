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
from quantbridge.accounts.account_state_machine import AccountStateMachine
from quantbridge.risk.account_limits import AccountLimits
from quantbridge.risk.prop_guard import PropGuard
from quantbridge.risk.risk_engine import RiskSnapshot, TradeIntent


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
    parser.add_argument("--account-state-file", default="state/account_states.json")
    parser.add_argument("--account-status", choices=["demo", "challenge", "funded", "paused", "breached", "disabled"], default=None)
    parser.add_argument("--strategy", default="OCLW")
    parser.add_argument("--direction", choices=["BUY", "SELL"], default="BUY")
    parser.add_argument("--units", type=float, default=None)
    parser.add_argument("--sl", type=float, default=None)
    parser.add_argument("--tp", type=float, default=None)
    parser.add_argument("--comment", default="order_lifecycle_check")
    parser.add_argument("--close-after", action="store_true")
    parser.add_argument("--risk-per-trade-pct", type=float, default=None)
    parser.add_argument("--daily-dd-limit-pct", type=float, default=5.0)
    parser.add_argument("--total-dd-limit-pct", type=float, default=10.0)
    parser.add_argument("--max-open-risk-pct", type=float, default=3.0)
    parser.add_argument("--max-risk-per-trade-pct", type=float, default=1.0)
    parser.add_argument("--max-concurrent-positions", type=int, default=3)
    parser.add_argument("--symbol-exposure-limit-pct", type=float, default=2.0)
    parser.add_argument("--min-units-per-trade", type=float, default=1.0)
    parser.add_argument("--max-units-per-trade", type=float, default=1000.0)
    parser.add_argument("--start-of-day-balance", type=float, default=None)
    parser.add_argument("--start-balance", type=float, default=None)
    parser.add_argument("--open-risk-pct", type=float, default=0.0)
    parser.add_argument("--symbol-exposure-pct", type=float, default=0.0)
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
        account_id=account_id,
        account_state_machine=AccountStateMachine(path=args.account_state_file),
        alert_callback=alert_callback,
    )
    if args.account_status is not None:
        runtime.account_state_machine.set_state(
            account_id=account_id,
            status=args.account_status,  # type: ignore[arg-type]
            reason="order_cli_override",
        )
    limits = AccountLimits(
        daily_drawdown_limit_pct=args.daily_dd_limit_pct,
        total_drawdown_limit_pct=args.total_dd_limit_pct,
        max_open_risk_pct=args.max_open_risk_pct,
        max_risk_per_trade_pct=args.max_risk_per_trade_pct,
        max_concurrent_positions=args.max_concurrent_positions,
        symbol_exposure_limit_pct=args.symbol_exposure_limit_pct,
        min_units_per_trade=args.min_units_per_trade,
        max_units_per_trade=args.max_units_per_trade,
    )
    guard = PropGuard(limits=limits)

    def _risk_check(intent: TradeIntent):
        account_state = broker.get_account_state()
        open_positions = broker.sync_positions(instrument=None)
        if account_state is None:
            equity = 0.0
            start_balance = 0.0
            start_of_day_balance = 0.0
        else:
            equity = float(account_state.equity)
            start_balance = float(args.start_balance) if args.start_balance is not None else float(account_state.balance)
            start_of_day_balance = (
                float(args.start_of_day_balance) if args.start_of_day_balance is not None else float(account_state.balance)
            )

        pause_exists = Path(args.pause_file).exists()
        snapshot = RiskSnapshot(
            equity=equity,
            start_of_day_balance=start_of_day_balance,
            start_balance=start_balance,
            open_positions=len(open_positions),
            open_risk_pct=float(args.open_risk_pct),
            symbol_exposure_pct={intent.instrument.upper(): float(args.symbol_exposure_pct)},
            trading_paused=pause_exists or runtime.paused,
            account_breached=False,
        )
        return guard.evaluate(intent=intent, snapshot=snapshot)

    manager = OrderManager(
        broker=broker,
        failsafe_callback=lambda reason: runtime.trigger_external_failsafe(
            reason=f"order_layer:{reason}",
            instrument=instrument,
        ),
        risk_check_callback=_risk_check,
    )

    if not broker.connect():
        print(json.dumps({"success": False, "error": "connect_failed"}))
        return 1

    pause_reason = runtime.account_state_machine.get_pause_reason(account_id)
    if pause_reason:
        print(
            json.dumps(
                {
                    "success": False,
                    "status": "account_blocked",
                    "error": f"account_state_blocked:{pause_reason}",
                    "account_id": account_id,
                },
                indent=2,
            )
        )
        return 3

    result = manager.place_and_validate(
        instrument=instrument,
        direction=args.direction,
        units=units,
        sl=args.sl,
        tp=args.tp,
        comment=args.comment,
        client_order_ref=f"order-{uuid.uuid4().hex[:10]}",
        enforce_protection=(args.sl is not None or args.tp is not None),
        risk_per_trade_pct=args.risk_per_trade_pct,
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
