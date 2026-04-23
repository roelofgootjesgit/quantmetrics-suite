from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import uuid

import yaml

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from quantbridge.accounts.account_policy import AccountPolicy
from quantbridge.accounts.account_state_machine import AccountStateMachine
from quantbridge.execution.brokers.ctrader_broker import CTraderBroker
from quantbridge.execution.order_manager import OrderManager
from quantbridge.router.account_selector import AccountRuntimeStatus, AccountSelector
from quantbridge.router.execution_orchestrator import MultiAccountExecutionOrchestrator
from quantbridge.router.execution_plan_builder import ExecutionPlanBuilder, TradeRequest
from quantbridge.ops.observability import JsonlEventSink
from quantbridge.risk.account_limits import AccountLimits
from quantbridge.risk.prop_guard import PropGuard
from quantbridge.risk.risk_engine import RiskSnapshot, TradeIntent


def load_config(path: str) -> dict:
    cfg_path = Path(path)
    if not cfg_path.is_absolute():
        cfg_path = ROOT / cfg_path
    with open(cfg_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def parse_policies(config: dict) -> list[AccountPolicy]:
    out: list[AccountPolicy] = []
    for raw in config.get("accounts", []) or []:
        limits_raw = raw.get("limits", {}) or {}
        limits = AccountLimits(
            daily_drawdown_limit_pct=float(limits_raw.get("daily_drawdown_limit_pct", 5.0)),
            total_drawdown_limit_pct=float(limits_raw.get("total_drawdown_limit_pct", 10.0)),
            max_open_risk_pct=float(limits_raw.get("max_open_risk_pct", 3.0)),
            max_risk_per_trade_pct=float(limits_raw.get("max_risk_per_trade_pct", 1.0)),
            max_concurrent_positions=int(limits_raw.get("max_concurrent_positions", 3)),
            symbol_exposure_limit_pct=float(limits_raw.get("symbol_exposure_limit_pct", 2.0)),
            min_units_per_trade=float(limits_raw.get("min_units_per_trade", 1.0)),
            max_units_per_trade=float(limits_raw.get("max_units_per_trade", 1000.0)),
        )
        out.append(
            AccountPolicy(
                account_id=str(raw.get("account_id", "")),
                mode=str(raw.get("mode", "demo")),  # type: ignore[arg-type]
                enabled=bool(raw.get("enabled", True)),
                priority=int(raw.get("priority", 100)),
                routing_mode=str(raw.get("routing_mode", "primary")),  # type: ignore[arg-type]
                account_group=str(raw.get("account_group", "default")),
                sizing_multiplier=float(raw.get("sizing_multiplier", 1.0)),
                allowed_symbols=[str(s).upper() for s in (raw.get("allowed_symbols", []) or [])],
                limits=limits,
            )
        )
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Run multi-account execution policy check in mock mode.")
    parser.add_argument("--config", default="configs/accounts_baseline.yaml")
    parser.add_argument("--instrument", default="XAUUSD")
    parser.add_argument("--direction", choices=["BUY", "SELL"], default="BUY")
    parser.add_argument("--units", type=float, default=100.0)
    parser.add_argument("--sl", type=float, default=None)
    parser.add_argument("--tp", type=float, default=None)
    parser.add_argument("--routing-mode", choices=["single", "primary_backup", "fanout"], default="single")
    parser.add_argument("--max-fanout-accounts", type=int, default=None)
    parser.add_argument("--account-group", default="core")
    parser.add_argument("--pause-account", action="append", default=[])
    parser.add_argument("--unhealthy-account", action="append", default=[])
    parser.add_argument("--runtime-paused-account", action="append", default=[])
    parser.add_argument("--missing-creds-account", action="append", default=[])
    parser.add_argument("--open-positions", action="append", default=[], help="Format ACCOUNT_ID:COUNT")
    parser.add_argument("--account-state-file", default="state/account_states.json")
    parser.add_argument("--events-file", default="")
    args = parser.parse_args()

    config = load_config(args.config)
    policies = parse_policies(config)
    account_machine = AccountStateMachine(path=args.account_state_file)
    for account_id in args.pause_account:
        account_machine.pause(account_id=str(account_id), reason="multi_account_check_pause")

    selector = AccountSelector(state_machine=account_machine)
    plan_builder = ExecutionPlanBuilder(selector=selector)
    event_sink = JsonlEventSink(path=args.events_file, source="execution") if args.events_file else None

    runtime_status: dict[str, AccountRuntimeStatus] = {}
    for account_id in args.runtime_paused_account:
        runtime_status[str(account_id)] = AccountRuntimeStatus(runtime_paused=True)
    for account_id in args.missing_creds_account:
        prev = runtime_status.get(str(account_id), AccountRuntimeStatus())
        runtime_status[str(account_id)] = AccountRuntimeStatus(
            broker_healthy=prev.broker_healthy,
            runtime_paused=prev.runtime_paused,
            has_credentials=False,
            open_positions=prev.open_positions,
        )
    for raw in args.open_positions:
        if ":" not in raw:
            continue
        account_id, count_text = raw.split(":", 1)
        try:
            count = int(count_text)
        except ValueError:
            continue
        prev = runtime_status.get(str(account_id), AccountRuntimeStatus())
        runtime_status[str(account_id)] = AccountRuntimeStatus(
            broker_healthy=prev.broker_healthy,
            runtime_paused=prev.runtime_paused,
            has_credentials=prev.has_credentials,
            open_positions=count,
        )

    managers: dict[str, OrderManager] = {}
    for policy in policies:
        broker = CTraderBroker(
            account_id=policy.account_id,
            access_token="",
            instrument=args.instrument,
            mode="mock",
        )
        broker.connect()
        guard = PropGuard(limits=policy.limits)

        def _risk_check(intent: TradeIntent, _broker=broker, _guard=guard):
            state = _broker.get_account_state()
            positions = _broker.sync_positions(instrument=None)
            equity = float(state.equity) if state else 0.0
            balance = float(state.balance) if state else 0.0
            snapshot = RiskSnapshot(
                equity=equity,
                start_of_day_balance=balance,
                start_balance=balance,
                open_positions=len(positions),
                open_risk_pct=0.0,
                symbol_exposure_pct={intent.instrument.upper(): 0.0},
                trading_paused=False,
                account_breached=False,
            )
            return _guard.evaluate(intent=intent, snapshot=snapshot)

        managers[policy.account_id] = OrderManager(
            broker=broker,
            risk_check_callback=_risk_check,
        )

    orchestrator = MultiAccountExecutionOrchestrator(
        plan_builder=plan_builder,
        order_manager_factory=lambda account_id: managers[str(account_id)],
        event_callback=(event_sink.emit if event_sink else None),
    )
    rid = uuid.uuid4().hex[:10]
    request = TradeRequest(
        instrument=args.instrument.upper(),
        direction=args.direction,
        units=float(args.units),
        sl=args.sl,
        tp=args.tp,
        comment="multi_account_execution_check",
        client_order_ref=f"plan-{rid}",
        strategy="OCLW",
        account_group=args.account_group,
        routing_mode=args.routing_mode,  # type: ignore[arg-type]
        max_fanout_accounts=args.max_fanout_accounts,
        trace_id=f"trace_exec_{rid}",
        decision_cycle_id=f"dc_exec_{rid}",
    )
    aggregate = orchestrator.execute(
        request=request,
        policies=policies,
        unhealthy_account_ids=[str(v) for v in args.unhealthy_account],
        runtime_status_by_account=runtime_status,
    )
    print(json.dumps(aggregate.__dict__, default=lambda o: o.__dict__, indent=2))
    return 0 if aggregate.overall_success else 2


if __name__ == "__main__":
    raise SystemExit(main())
