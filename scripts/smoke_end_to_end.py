"""QuantLog end-to-end smoke acceptance runner.

This script emits events through adapters and validates the full pipeline:
- emit
- validate
- replay
- summarize
- ingest health
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from quantlog.ingest.adapters import QuantBridgeEmitter, QuantBuildEmitter
from quantlog.ingest.health import detect_audit_gaps
from quantlog.replay.service import replay_trace
from quantlog.summarize.service import summarize_path
from quantlog.validate.validator import validate_path


@dataclass(slots=True, frozen=True)
class ScenarioContext:
    trace_id: str
    order_ref: str
    position_id: str
    decision_cycle_id: str
    trade_id: str


def _new_context(prefix: str) -> ScenarioContext:
    suffix = uuid4().hex[:10]
    tid = f"trade_{prefix}_{suffix}"
    return ScenarioContext(
        trace_id=f"trace_{prefix}_{suffix}",
        order_ref=f"ord_{prefix}_{suffix}",
        position_id=f"pos_{prefix}_{suffix}",
        decision_cycle_id=f"dc_{prefix}_{suffix}",
        trade_id=tid,
    )


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _emit_happy_path(
    *,
    qb: QuantBuildEmitter,
    qbr: QuantBridgeEmitter,
    ctx: ScenarioContext,
    account_id: str,
    strategy_id: str,
    symbol: str,
) -> None:
    qb.emit(
        event_type="signal_evaluated",
        trace_id=ctx.trace_id,
        decision_cycle_id=ctx.decision_cycle_id,
        account_id=account_id,
        strategy_id=strategy_id,
        symbol=symbol,
        payload={
            "signal_type": "ict_sweep",
            "signal_direction": "LONG",
            "confidence": 0.64,
        },
        timestamp_utc="2026-03-29T18:00:00Z",
    )
    qb.emit(
        event_type="risk_guard_decision",
        trace_id=ctx.trace_id,
        decision_cycle_id=ctx.decision_cycle_id,
        account_id=account_id,
        strategy_id=strategy_id,
        symbol=symbol,
        payload={
            "guard_name": "spread_guard",
            "decision": "ALLOW",
            "reason": "spread_ok",
        },
        timestamp_utc="2026-03-29T18:00:01Z",
    )
    qb.emit(
        event_type="trade_action",
        trace_id=ctx.trace_id,
        decision_cycle_id=ctx.decision_cycle_id,
        account_id=account_id,
        strategy_id=strategy_id,
        symbol=symbol,
        payload={
            "decision": "ENTER",
            "reason": "all_guards_passed",
            "side": "BUY",
            "trade_id": ctx.trade_id,
        },
        timestamp_utc="2026-03-29T18:00:02Z",
    )
    qbr.emit(
        event_type="order_submitted",
        trace_id=ctx.trace_id,
        decision_cycle_id=ctx.decision_cycle_id,
        order_ref=ctx.order_ref,
        account_id=account_id,
        strategy_id=strategy_id,
        symbol=symbol,
        payload={
            "order_ref": ctx.order_ref,
            "side": "BUY",
            "volume": 0.5,
            "trade_id": ctx.trade_id,
            "decision_cycle_id": ctx.decision_cycle_id,
        },
        timestamp_utc="2026-03-29T18:00:03Z",
    )
    qbr.emit(
        event_type="order_filled",
        trace_id=ctx.trace_id,
        decision_cycle_id=ctx.decision_cycle_id,
        order_ref=ctx.order_ref,
        position_id=ctx.position_id,
        account_id=account_id,
        strategy_id=strategy_id,
        symbol=symbol,
        payload={
            "order_ref": ctx.order_ref,
            "fill_price": 2351.42,
            "slippage": 0.12,
            "trade_id": ctx.trade_id,
            "decision_cycle_id": ctx.decision_cycle_id,
        },
        timestamp_utc="2026-03-29T18:00:04Z",
    )


def _emit_block_path(
    *,
    qb: QuantBuildEmitter,
    ctx: ScenarioContext,
    account_id: str,
    strategy_id: str,
    symbol: str,
) -> None:
    qb.emit(
        event_type="signal_evaluated",
        trace_id=ctx.trace_id,
        decision_cycle_id=ctx.decision_cycle_id,
        account_id=account_id,
        strategy_id=strategy_id,
        symbol=symbol,
        payload={
            "signal_type": "ict_sweep",
            "signal_direction": "SHORT",
            "confidence": 0.58,
        },
        timestamp_utc="2026-03-29T18:01:00Z",
    )
    qb.emit(
        event_type="risk_guard_decision",
        trace_id=ctx.trace_id,
        decision_cycle_id=ctx.decision_cycle_id,
        account_id=account_id,
        strategy_id=strategy_id,
        symbol=symbol,
        payload={
            "guard_name": "spread_guard",
            "decision": "BLOCK",
            "reason": "spread_too_wide",
        },
        timestamp_utc="2026-03-29T18:01:01Z",
    )
    qb.emit(
        event_type="trade_action",
        trace_id=ctx.trace_id,
        decision_cycle_id=ctx.decision_cycle_id,
        account_id=account_id,
        strategy_id=strategy_id,
        symbol=symbol,
        payload={
            "decision": "NO_ACTION",
            "reason": "spread_too_high",
            "side": "SELL",
        },
        timestamp_utc="2026-03-29T18:01:02Z",
    )


def run_smoke() -> None:
    with tempfile.TemporaryDirectory(prefix="quantlog_smoke_") as tmp_dir:
        events_root = Path(tmp_dir) / "events"
        account_id = "paper_smoke_01"
        strategy_id = "xau_smoke_v1"
        symbol = "XAUUSD"
        run_id = f"run_smoke_{uuid4().hex[:8]}"
        session_id = f"session_smoke_{uuid4().hex[:8]}"

        qb = QuantBuildEmitter.from_base_path(
            base_path=events_root,
            environment="paper",
            run_id=run_id,
            session_id=session_id,
            source_component="quantbuild_smoke",
        )
        qbr = QuantBridgeEmitter.from_base_path(
            base_path=events_root,
            environment="paper",
            run_id=run_id,
            session_id=session_id,
            source_component="quantbridge_smoke",
        )

        happy = _new_context("happy")
        blocked = _new_context("blocked")

        _emit_happy_path(
            qb=qb,
            qbr=qbr,
            ctx=happy,
            account_id=account_id,
            strategy_id=strategy_id,
            symbol=symbol,
        )
        _emit_block_path(
            qb=qb,
            ctx=blocked,
            account_id=account_id,
            strategy_id=strategy_id,
            symbol=symbol,
        )
        print("[OK] emit scenario")

        report = validate_path(events_root)
        errors_total = sum(1 for issue in report.issues if issue.level == "error")
        _assert(errors_total == 0, f"validate failed with {errors_total} errors")
        print("[OK] validate events")

        replay_happy = replay_trace(events_root, happy.trace_id)
        _assert(len(replay_happy) == 5, f"happy replay count mismatch: {len(replay_happy)}")
        _assert(replay_happy[0].event_type == "signal_evaluated", "happy replay must start with signal")
        _assert(
            replay_happy[-1].event_type == "order_filled",
            "happy replay must end with order_filled",
        )
        for i in range(1, len(replay_happy)):
            prev = replay_happy[i - 1]
            cur = replay_happy[i]
            if prev.timestamp_utc == cur.timestamp_utc:
                _assert(
                    prev.source_seq <= cur.source_seq,
                    "source_seq ordering failed on equal timestamp",
                )

        replay_blocked = replay_trace(events_root, blocked.trace_id)
        _assert(len(replay_blocked) == 3, f"blocked replay count mismatch: {len(replay_blocked)}")
        _assert(
            replay_blocked[-1].payload.get("decision") == "NO_ACTION",
            "blocked replay must end with NO_ACTION",
        )
        print("[OK] replay trace")

        summary = summarize_path(events_root)
        by_type = summary.by_event_type
        _assert(by_type.get("signal_evaluated", 0) == 2, "summary signal count mismatch")
        _assert(by_type.get("risk_guard_decision", 0) == 2, "summary guard count mismatch")
        _assert(by_type.get("trade_action", 0) == 2, "summary trade_action count mismatch")
        _assert(by_type.get("order_submitted", 0) == 1, "summary order_submitted mismatch")
        _assert(by_type.get("order_filled", 0) == 1, "summary order_filled mismatch")
        _assert(summary.trades_attempted == 1, "summary trades_attempted mismatch")
        _assert(summary.trades_filled == 1, "summary trades_filled mismatch")
        _assert(summary.blocks_total == 1, "summary blocks_total mismatch")
        _assert(summary.broker_rejects == 0, "summary broker_rejects mismatch")
        _assert(
            summary.trade_action_by_decision.get("ENTER") == 1,
            "summary trade_action ENTER count mismatch",
        )
        _assert(
            summary.trade_action_by_decision.get("NO_ACTION") == 1,
            "summary trade_action NO_ACTION count mismatch",
        )
        _assert(
            summary.no_action_by_reason.get("spread_too_high") == 1,
            "summary no_action_by_reason spread_too_high mismatch",
        )
        _assert(
            summary.risk_guard_blocks_by_guard.get("spread_guard") == 1,
            "summary risk_guard_blocks_by_guard mismatch",
        )
        print("[OK] summarize day")

        gaps = detect_audit_gaps(events_root, max_gap_seconds=300.0)
        _assert(len(gaps) == 0, f"ingest health found unexpected gaps: {len(gaps)}")
        print("[OK] ingest health")

        print("SMOKE END-TO-END PASSED")


def main() -> int:
    try:
        run_smoke()
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"[FAIL] {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

