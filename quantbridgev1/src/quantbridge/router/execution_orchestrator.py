from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Optional
from uuid import uuid4

from quantbridge.execution.order_manager import OrderLifecycleResult
from quantbridge.router.execution_plan_builder import ExecutionPlanBuilder, TradeRequest
from quantbridge.router.account_selector import AccountRuntimeStatus


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class AccountExecutionResult:
    account_id: str
    attempted: bool
    success: bool
    status: str
    role: str
    message: str = ""
    error: str | None = None
    trade_id: str | None = None
    order_id: str | None = None
    filled_units: float | None = None
    risk_decision: dict | None = None
    order_ref: str | None = None
    requested_price: float | None = None
    fill_price: float | None = None
    slippage: float | None = None
    fill_latency_ms: float | None = None
    spread_at_fill: float | None = None


@dataclass(frozen=True)
class AggregateExecutionResult:
    routing_mode: str
    overall_success: bool
    any_success: bool
    all_success: bool
    results: list[AccountExecutionResult] = field(default_factory=list)
    skipped: list[dict] = field(default_factory=list)
    timestamp: str = field(default_factory=_utc_now_iso)


class MultiAccountExecutionOrchestrator:
    """Execute one trade intent across accounts based on execution policy."""

    def __init__(
        self,
        plan_builder: ExecutionPlanBuilder,
        order_manager_factory: Callable[[str], object],
        event_callback: Optional[Callable[[str, dict], None]] = None,
    ) -> None:
        self.plan_builder = plan_builder
        self.order_manager_factory = order_manager_factory
        self.event_callback = event_callback

    def _emit_event(self, event_type: str, payload: dict) -> None:
        if self.event_callback is None:
            return
        try:
            self.event_callback(event_type, payload)
        except Exception:
            pass

    def _to_result(self, account_id: str, role: str, lifecycle: OrderLifecycleResult) -> AccountExecutionResult:
        return AccountExecutionResult(
            account_id=account_id,
            attempted=True,
            success=bool(lifecycle.success),
            status=str(lifecycle.status),
            role=role,
            message=lifecycle.message,
            error=lifecycle.error,
            trade_id=lifecycle.trade_id,
            order_id=lifecycle.order_id,
            filled_units=lifecycle.filled_units,
            risk_decision=lifecycle.risk_decision,
            order_ref=lifecycle.order_ref,
            requested_price=lifecycle.requested_price,
            fill_price=lifecycle.fill_price,
            slippage=lifecycle.slippage,
            fill_latency_ms=lifecycle.fill_latency_ms,
            spread_at_fill=lifecycle.spread_at_fill,
        )

    def _quantlog_trace_id(self, request: TradeRequest) -> str:
        tid = str(getattr(request, "trace_id", "") or "").strip()
        if tid:
            return tid
        return f"trace_qbr_{uuid4().hex[:12]}"

    @staticmethod
    def _quantlog_trade_id(request: TradeRequest, lc: OrderLifecycleResult) -> str | None:
        if lc.trade_id and str(lc.trade_id).strip():
            return str(lc.trade_id).strip()
        ext = str(getattr(request, "trade_id", "") or "").strip()
        return ext or None

    @staticmethod
    def _quantlog_decision_cycle_id(request: TradeRequest) -> str | None:
        dc = str(getattr(request, "decision_cycle_id", "") or "").strip()
        return dc or None

    @staticmethod
    def _direction_to_trade_executed(direction: str) -> str:
        """Map order/broker side to QuantLog trade_executed.direction (LONG|SHORT)."""
        d = (direction or "").strip().upper()
        if d in ("BUY", "LONG"):
            return "LONG"
        if d in ("SELL", "SHORT"):
            return "SHORT"
        return d or "LONG"

    def _emit_quantlog_execution_events(self, request: TradeRequest, account_id: str, lc: OrderLifecycleResult) -> None:
        """Emit canonical QuantLog-shaped events when event_callback is wired (JSONL sink)."""
        if self.event_callback is None:
            return
        trace = self._quantlog_trace_id(request)
        base: dict = {
            "trace_id": trace,
            "account_id": account_id,
            "symbol": request.instrument,
            "instrument": request.instrument,
            "strategy_id": request.strategy,
        }
        q_tid = self._quantlog_trade_id(request, lc)
        q_dc = self._quantlog_decision_cycle_id(request)
        if not q_dc:
            q_dc = f"dc_bridge_{uuid4().hex[:16]}"
        if lc.status != "risk_blocked" and (lc.order_id or lc.order_ref) and q_tid:
            sub_payload = {
                **base,
                "order_ref": lc.order_ref or str(lc.order_id or ""),
                "side": request.direction,
                "volume": float(request.units),
                "trade_id": q_tid,
                "decision_cycle_id": q_dc,
            }
            self._emit_event("order_submitted", sub_payload)
        if lc.fill_confirmed and lc.trade_id:
            fill_payload = {
                **base,
                "trade_id": lc.trade_id,
                "order_ref": lc.order_ref or str(lc.order_id or ""),
                "requested_price": lc.requested_price,
                "fill_price": lc.fill_price,
                "slippage": lc.slippage,
                "fill_latency_ms": lc.fill_latency_ms,
                "spread_at_fill": lc.spread_at_fill,
                "decision_cycle_id": q_dc,
            }
            self._emit_event("order_filled", fill_payload)
            oref = lc.order_ref or str(lc.order_id or "")
            if q_tid and oref:
                te_payload = {
                    **base,
                    "trade_id": q_tid,
                    "order_ref": oref,
                    "direction": self._direction_to_trade_executed(request.direction),
                    "decision_cycle_id": q_dc,
                }
                self._emit_event("trade_executed", te_payload)

    def execute(
        self,
        *,
        request: TradeRequest,
        policies: list,
        unhealthy_account_ids: list[str] | None = None,
        runtime_status_by_account: dict[str, AccountRuntimeStatus] | None = None,
    ) -> AggregateExecutionResult:
        plan = self.plan_builder.build(
            request=request,
            policies=policies,
            unhealthy_account_ids=unhealthy_account_ids,
            runtime_status_by_account=runtime_status_by_account,
        )

        results: list[AccountExecutionResult] = []
        self._emit_event(
            "execution.plan.built",
            {
                "routing_mode": plan.routing_mode,
                "instrument": plan.instrument,
                "direction": plan.direction,
                "planned_accounts": [item.account_id for item in plan.items],
                "planned_count": len(plan.items),
                "skipped_count": len(plan.skipped),
            },
        )
        if not plan.items:
            return AggregateExecutionResult(
                routing_mode=plan.routing_mode,
                overall_success=False,
                any_success=False,
                all_success=False,
                results=[],
                skipped=plan.skipped,
            )

        if plan.routing_mode == "single":
            item = plan.items[0]
            manager = self.order_manager_factory(item.account_id)
            lifecycle = manager.place_and_validate(
                instrument=request.instrument,
                direction=request.direction,
                units=item.planned_units,
                sl=request.sl,
                tp=request.tp,
                comment=request.comment,
                client_order_ref=request.client_order_ref,
                enforce_protection=(request.sl is not None or request.tp is not None),
            )
            results.append(self._to_result(item.account_id, item.role, lifecycle))
            self._emit_quantlog_execution_events(request, item.account_id, lifecycle)
            self._emit_event(
                "execution.account.result",
                {
                    "account_id": item.account_id,
                    "role": item.role,
                    "attempted": True,
                    "success": bool(lifecycle.success),
                    "status": lifecycle.status,
                    "error": lifecycle.error,
                },
            )

        elif plan.routing_mode == "primary_backup":
            success_seen = False
            for item in plan.items:
                if success_seen:
                    results.append(
                        AccountExecutionResult(
                            account_id=item.account_id,
                            attempted=False,
                            success=False,
                            status="not_attempted_after_success",
                            role=item.role,
                            message="previous_account_succeeded",
                        )
                    )
                    self._emit_event(
                        "execution.account.result",
                        {
                            "account_id": item.account_id,
                            "role": item.role,
                            "attempted": False,
                            "success": False,
                            "status": "not_attempted_after_success",
                            "error": None,
                        },
                    )
                    continue
                manager = self.order_manager_factory(item.account_id)
                lifecycle = manager.place_and_validate(
                    instrument=request.instrument,
                    direction=request.direction,
                    units=item.planned_units,
                    sl=request.sl,
                    tp=request.tp,
                    comment=request.comment,
                    client_order_ref=request.client_order_ref,
                    enforce_protection=(request.sl is not None or request.tp is not None),
                )
                result = self._to_result(item.account_id, item.role, lifecycle)
                results.append(result)
                self._emit_quantlog_execution_events(request, item.account_id, lifecycle)
                self._emit_event(
                    "execution.account.result",
                    {
                        "account_id": item.account_id,
                        "role": item.role,
                        "attempted": True,
                        "success": bool(result.success),
                        "status": result.status,
                        "error": result.error,
                    },
                )
                if result.success:
                    success_seen = True

        else:  # fanout
            for item in plan.items:
                manager = self.order_manager_factory(item.account_id)
                lifecycle = manager.place_and_validate(
                    instrument=request.instrument,
                    direction=request.direction,
                    units=item.planned_units,
                    sl=request.sl,
                    tp=request.tp,
                    comment=request.comment,
                    client_order_ref=request.client_order_ref,
                    enforce_protection=(request.sl is not None or request.tp is not None),
                )
                results.append(self._to_result(item.account_id, item.role, lifecycle))
                self._emit_quantlog_execution_events(request, item.account_id, lifecycle)
                self._emit_event(
                    "execution.account.result",
                    {
                        "account_id": item.account_id,
                        "role": item.role,
                        "attempted": True,
                        "success": bool(lifecycle.success),
                        "status": lifecycle.status,
                        "error": lifecycle.error,
                    },
                )

        any_success = any(result.success for result in results)
        attempted_results = [result for result in results if result.attempted]
        all_success = bool(attempted_results) and all(result.success for result in attempted_results)
        overall_success = any_success if plan.routing_mode in {"primary_backup", "single"} else all_success

        aggregate = AggregateExecutionResult(
            routing_mode=plan.routing_mode,
            overall_success=overall_success,
            any_success=any_success,
            all_success=all_success,
            results=results,
            skipped=plan.skipped,
        )
        self._emit_event(
            "execution.aggregate.result",
            {
                "routing_mode": aggregate.routing_mode,
                "overall_success": aggregate.overall_success,
                "any_success": aggregate.any_success,
                "all_success": aggregate.all_success,
                "result_count": len(aggregate.results),
                "skipped_count": len(aggregate.skipped),
            },
        )
        return aggregate

