"""Generate a synthetic QuantLog event day for replay/metrics testing.

Scenarios:
- happy
- blocked
- rejected
- partial_fill
- governance_pause
- failsafe_pause
- adaptive_mode
"""

from __future__ import annotations

import argparse
import random
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from quantlog.ingest.adapters import QuantBridgeEmitter, QuantBuildEmitter


@dataclass(slots=True, frozen=True)
class TraceIds:
    trace_id: str
    order_ref: str
    position_id: str
    decision_cycle_id: str
    trade_id: str


def _mk_ids(prefix: str, idx: int) -> TraceIds:
    suffix = uuid4().hex[:8]
    return TraceIds(
        trace_id=f"trace_{prefix}_{idx}_{suffix}",
        order_ref=f"ord_{prefix}_{idx}_{suffix}",
        position_id=f"pos_{prefix}_{idx}_{suffix}",
        decision_cycle_id=f"dc_{prefix}_{idx}_{suffix}",
        trade_id=f"trade_{prefix}_{idx}_{suffix}",
    )


def _fmt(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _emit_happy(
    qb: QuantBuildEmitter,
    qbr: QuantBridgeEmitter,
    ids: TraceIds,
    base_dt: datetime,
    account_id: str,
    strategy_id: str,
    symbol: str,
) -> None:
    qb.emit(
        event_type="signal_evaluated",
        trace_id=ids.trace_id,
        decision_cycle_id=ids.decision_cycle_id,
        account_id=account_id,
        strategy_id=strategy_id,
        symbol=symbol,
        timestamp_utc=_fmt(base_dt + timedelta(seconds=0)),
        payload={"signal_type": "ict_sweep", "signal_direction": "LONG", "confidence": 0.65},
    )
    qb.emit(
        event_type="risk_guard_decision",
        trace_id=ids.trace_id,
        decision_cycle_id=ids.decision_cycle_id,
        account_id=account_id,
        strategy_id=strategy_id,
        symbol=symbol,
        timestamp_utc=_fmt(base_dt + timedelta(seconds=1)),
        payload={"guard_name": "spread_guard", "decision": "ALLOW", "reason": "spread_ok"},
    )
    qb.emit(
        event_type="trade_action",
        trace_id=ids.trace_id,
        decision_cycle_id=ids.decision_cycle_id,
        account_id=account_id,
        strategy_id=strategy_id,
        symbol=symbol,
        timestamp_utc=_fmt(base_dt + timedelta(seconds=2)),
        payload={
            "decision": "ENTER",
            "reason": "all_guards_passed",
            "side": "BUY",
            "trade_id": ids.trade_id,
        },
    )
    qbr.emit(
        event_type="order_submitted",
        trace_id=ids.trace_id,
        decision_cycle_id=ids.decision_cycle_id,
        order_ref=ids.order_ref,
        account_id=account_id,
        strategy_id=strategy_id,
        symbol=symbol,
        timestamp_utc=_fmt(base_dt + timedelta(seconds=3)),
        payload={
            "order_ref": ids.order_ref,
            "side": "BUY",
            "volume": 0.5,
            "trade_id": ids.trade_id,
            "decision_cycle_id": ids.decision_cycle_id,
        },
    )
    qbr.emit(
        event_type="order_filled",
        trace_id=ids.trace_id,
        decision_cycle_id=ids.decision_cycle_id,
        order_ref=ids.order_ref,
        position_id=ids.position_id,
        account_id=account_id,
        strategy_id=strategy_id,
        symbol=symbol,
        timestamp_utc=_fmt(base_dt + timedelta(seconds=4)),
        payload={
            "order_ref": ids.order_ref,
            "fill_price": 2350.0,
            "slippage": 0.08,
            "trade_id": ids.trade_id,
            "decision_cycle_id": ids.decision_cycle_id,
        },
    )


def _emit_blocked(
    qb: QuantBuildEmitter,
    ids: TraceIds,
    base_dt: datetime,
    account_id: str,
    strategy_id: str,
    symbol: str,
) -> None:
    qb.emit(
        event_type="signal_evaluated",
        trace_id=ids.trace_id,
        decision_cycle_id=ids.decision_cycle_id,
        account_id=account_id,
        strategy_id=strategy_id,
        symbol=symbol,
        timestamp_utc=_fmt(base_dt + timedelta(seconds=0)),
        payload={"signal_type": "ict_sweep", "signal_direction": "SHORT", "confidence": 0.57},
    )
    qb.emit(
        event_type="risk_guard_decision",
        trace_id=ids.trace_id,
        decision_cycle_id=ids.decision_cycle_id,
        account_id=account_id,
        strategy_id=strategy_id,
        symbol=symbol,
        timestamp_utc=_fmt(base_dt + timedelta(seconds=1)),
        payload={"guard_name": "spread_guard", "decision": "BLOCK", "reason": "spread_too_wide"},
    )
    qb.emit(
        event_type="trade_action",
        trace_id=ids.trace_id,
        decision_cycle_id=ids.decision_cycle_id,
        account_id=account_id,
        strategy_id=strategy_id,
        symbol=symbol,
        timestamp_utc=_fmt(base_dt + timedelta(seconds=2)),
        payload={"decision": "NO_ACTION", "reason": "spread_too_high", "side": "SELL"},
    )


def _emit_rejected(
    qb: QuantBuildEmitter,
    qbr: QuantBridgeEmitter,
    ids: TraceIds,
    base_dt: datetime,
    account_id: str,
    strategy_id: str,
    symbol: str,
) -> None:
    qb.emit(
        event_type="signal_evaluated",
        trace_id=ids.trace_id,
        decision_cycle_id=ids.decision_cycle_id,
        account_id=account_id,
        strategy_id=strategy_id,
        symbol=symbol,
        timestamp_utc=_fmt(base_dt + timedelta(seconds=0)),
        payload={"signal_type": "ict_sweep", "signal_direction": "LONG", "confidence": 0.6},
    )
    qb.emit(
        event_type="risk_guard_decision",
        trace_id=ids.trace_id,
        decision_cycle_id=ids.decision_cycle_id,
        account_id=account_id,
        strategy_id=strategy_id,
        symbol=symbol,
        timestamp_utc=_fmt(base_dt + timedelta(seconds=1)),
        payload={"guard_name": "spread_guard", "decision": "ALLOW", "reason": "spread_ok"},
    )
    qb.emit(
        event_type="trade_action",
        trace_id=ids.trace_id,
        decision_cycle_id=ids.decision_cycle_id,
        account_id=account_id,
        strategy_id=strategy_id,
        symbol=symbol,
        timestamp_utc=_fmt(base_dt + timedelta(seconds=2)),
        payload={
            "decision": "ENTER",
            "reason": "entry_allowed",
            "side": "BUY",
            "trade_id": ids.trade_id,
        },
    )
    qbr.emit(
        event_type="order_submitted",
        trace_id=ids.trace_id,
        decision_cycle_id=ids.decision_cycle_id,
        order_ref=ids.order_ref,
        account_id=account_id,
        strategy_id=strategy_id,
        symbol=symbol,
        timestamp_utc=_fmt(base_dt + timedelta(seconds=3)),
        payload={
            "order_ref": ids.order_ref,
            "side": "BUY",
            "volume": 0.5,
            "trade_id": ids.trade_id,
            "decision_cycle_id": ids.decision_cycle_id,
        },
    )
    qbr.emit(
        event_type="order_rejected",
        trace_id=ids.trace_id,
        decision_cycle_id=ids.decision_cycle_id,
        order_ref=ids.order_ref,
        account_id=account_id,
        strategy_id=strategy_id,
        symbol=symbol,
        timestamp_utc=_fmt(base_dt + timedelta(seconds=4)),
        payload={"order_ref": ids.order_ref, "reason": "insufficient_margin"},
    )


def _emit_partial_fill(
    qb: QuantBuildEmitter,
    qbr: QuantBridgeEmitter,
    ids: TraceIds,
    base_dt: datetime,
    account_id: str,
    strategy_id: str,
    symbol: str,
) -> None:
    _emit_happy(qb, qbr, ids, base_dt, account_id, strategy_id, symbol)
    qbr.emit(
        event_type="order_filled",
        trace_id=ids.trace_id,
        decision_cycle_id=ids.decision_cycle_id,
        order_ref=ids.order_ref,
        position_id=ids.position_id,
        account_id=account_id,
        strategy_id=strategy_id,
        symbol=symbol,
        timestamp_utc=_fmt(base_dt + timedelta(seconds=5)),
        payload={
            "order_ref": ids.order_ref,
            "fill_price": 2350.2,
            "slippage": 0.11,
            "partial_fill": True,
            "fill_fraction": 0.5,
            "trade_id": ids.trade_id,
            "decision_cycle_id": ids.decision_cycle_id,
        },
    )


def _emit_governance_pause(
    qb: QuantBuildEmitter,
    qbr: QuantBridgeEmitter,
    ids: TraceIds,
    base_dt: datetime,
    account_id: str,
    strategy_id: str,
    symbol: str,
) -> None:
    qb.emit(
        event_type="signal_evaluated",
        trace_id=ids.trace_id,
        decision_cycle_id=ids.decision_cycle_id,
        account_id=account_id,
        strategy_id=strategy_id,
        symbol=symbol,
        timestamp_utc=_fmt(base_dt + timedelta(seconds=0)),
        payload={"signal_type": "ict_sweep", "signal_direction": "LONG", "confidence": 0.61},
    )
    qbr.emit(
        event_type="governance_state_changed",
        trace_id=ids.trace_id,
        account_id=account_id,
        strategy_id=strategy_id,
        symbol=symbol,
        timestamp_utc=_fmt(base_dt + timedelta(seconds=1)),
        payload={
            "account_id": account_id,
            "old_state": "normal",
            "new_state": "paused",
            "reason": "daily_dd_limit",
        },
    )
    qb.emit(
        event_type="trade_action",
        trace_id=ids.trace_id,
        decision_cycle_id=ids.decision_cycle_id,
        account_id=account_id,
        strategy_id=strategy_id,
        symbol=symbol,
        timestamp_utc=_fmt(base_dt + timedelta(seconds=2)),
        payload={"decision": "NO_ACTION", "reason": "execution_disabled", "side": "BUY"},
    )


def _emit_failsafe_pause(
    qb: QuantBuildEmitter,
    qbr: QuantBridgeEmitter,
    ids: TraceIds,
    base_dt: datetime,
    account_id: str,
    strategy_id: str,
    symbol: str,
) -> None:
    qb.emit(
        event_type="signal_evaluated",
        trace_id=ids.trace_id,
        decision_cycle_id=ids.decision_cycle_id,
        account_id=account_id,
        strategy_id=strategy_id,
        symbol=symbol,
        timestamp_utc=_fmt(base_dt + timedelta(seconds=0)),
        payload={"signal_type": "ict_sweep", "signal_direction": "SHORT", "confidence": 0.54},
    )
    qbr.emit(
        event_type="failsafe_pause",
        trace_id=ids.trace_id,
        account_id=account_id,
        strategy_id=strategy_id,
        symbol=symbol,
        timestamp_utc=_fmt(base_dt + timedelta(seconds=1)),
        payload={"reason": "spread_spike", "spread": 45, "duration_seconds": 180},
    )
    qb.emit(
        event_type="trade_action",
        trace_id=ids.trace_id,
        decision_cycle_id=ids.decision_cycle_id,
        account_id=account_id,
        strategy_id=strategy_id,
        symbol=symbol,
        timestamp_utc=_fmt(base_dt + timedelta(seconds=2)),
        payload={"decision": "NO_ACTION", "reason": "execution_disabled", "side": "SELL"},
    )


def _emit_adaptive_mode(
    qb: QuantBuildEmitter,
    ids: TraceIds,
    base_dt: datetime,
    account_id: str,
    strategy_id: str,
    symbol: str,
) -> None:
    qb.emit(
        event_type="adaptive_mode_transition",
        trace_id=ids.trace_id,
        account_id=account_id,
        strategy_id=strategy_id,
        symbol=symbol,
        timestamp_utc=_fmt(base_dt + timedelta(seconds=0)),
        payload={
            "old_mode": "BASE",
            "new_mode": "DEFENSIVE",
            "reason": "drawdown_threshold",
        },
    )
    qb.emit(
        event_type="trade_action",
        trace_id=ids.trace_id,
        decision_cycle_id=ids.decision_cycle_id,
        account_id=account_id,
        strategy_id=strategy_id,
        symbol=symbol,
        timestamp_utc=_fmt(base_dt + timedelta(seconds=1)),
        payload={"decision": "NO_ACTION", "reason": "cooldown_active"},
    )


def _emit_session_restart_probe(
    output_path: Path,
    environment: str,
    run_id: str,
    session_id: str,
    base_dt: datetime,
    account_id: str,
    strategy_id: str,
    symbol: str,
) -> None:
    restarted_session_id = f"{session_id}_restart"
    qb_restart = QuantBuildEmitter.from_base_path(
        base_path=output_path,
        source_component="quantbuild_generator_restart",
        environment=environment,
        run_id=run_id,
        session_id=restarted_session_id,
    )
    ids = _mk_ids("restart_probe", 0)
    qb_restart.emit(
        event_type="signal_evaluated",
        trace_id=ids.trace_id,
        decision_cycle_id=ids.decision_cycle_id,
        account_id=account_id,
        strategy_id=strategy_id,
        symbol=symbol,
        timestamp_utc=_fmt(base_dt + timedelta(seconds=0)),
        payload={"signal_type": "restart_probe", "signal_direction": "LONG", "confidence": 0.5},
    )
    qb_restart.emit(
        event_type="trade_action",
        trace_id=ids.trace_id,
        decision_cycle_id=ids.decision_cycle_id,
        account_id=account_id,
        strategy_id=strategy_id,
        symbol=symbol,
        timestamp_utc=_fmt(base_dt + timedelta(seconds=1)),
        payload={"decision": "NO_ACTION", "reason": "session_blocked"},
    )


def _inject_anomalies(output_path: Path, date: str) -> dict[str, int]:
    stats = {"duplicates_injected": 0, "missing_trace_injected": 0, "out_of_order_injected": 0}
    day_dir = output_path / date
    qb_path = day_dir / "quantbuild.jsonl"
    if not qb_path.exists():
        return stats

    lines = qb_path.read_text(encoding="utf-8").splitlines()
    if not lines:
        return stats

    # Duplicate first event line (duplicate event_id)
    lines.append(lines[0])
    stats["duplicates_injected"] += 1

    # Create missing trace_id by removing field from a copy
    import json  # local import to keep script scope minimal

    first_obj = json.loads(lines[0])
    if "trace_id" in first_obj:
        first_obj.pop("trace_id")
        lines.append(json.dumps(first_obj, ensure_ascii=True))
        stats["missing_trace_injected"] += 1

    # Out-of-order: append event with old timestamp and low seq
    oo_obj = json.loads(lines[0])
    oo_obj["timestamp_utc"] = f"{date}T00:00:00Z"
    oo_obj["source_seq"] = 1
    oo_obj["event_id"] = f"out_of_order_{uuid4().hex[:12]}"
    lines.append(json.dumps(oo_obj, ensure_ascii=True))
    stats["out_of_order_injected"] += 1

    qb_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return stats


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate a sample QuantLog event day")
    parser.add_argument("--output-path", default="data/events/generated", help="Base output event path")
    parser.add_argument(
        "--date", default=datetime.now(tz=timezone.utc).strftime("%Y-%m-%d"), help="UTC date YYYY-MM-DD"
    )
    parser.add_argument("--traces", type=int, default=20, help="Total traces to generate")
    parser.add_argument("--happy-ratio", type=float, default=0.6, help="Happy path ratio")
    parser.add_argument("--blocked-ratio", type=float, default=0.25, help="Blocked path ratio")
    parser.add_argument("--rejected-ratio", type=float, default=0.15, help="Rejected path ratio")
    parser.add_argument("--partial-fill-ratio", type=float, default=0.05, help="Partial fill scenario ratio")
    parser.add_argument("--governance-ratio", type=float, default=0.04, help="Governance pause scenario ratio")
    parser.add_argument("--failsafe-ratio", type=float, default=0.03, help="Failsafe pause scenario ratio")
    parser.add_argument("--adaptive-ratio", type=float, default=0.03, help="Adaptive transition scenario ratio")
    parser.add_argument(
        "--include-session-restart-probe",
        action="store_true",
        help="Emit a small restart probe with new session_id in same run",
    )
    parser.add_argument(
        "--inject-anomalies",
        action="store_true",
        help="Inject duplicates/missing-trace/out-of-order anomalies for quality tests",
    )
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    parser.add_argument("--environment", default="paper", help="Event environment")
    parser.add_argument("--strategy-id", default="xau_sample_v1", help="Strategy id")
    parser.add_argument("--account-id", default="paper_01", help="Account id")
    parser.add_argument("--symbol", default="XAUUSD", help="Symbol")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    output_path = Path(args.output_path)
    rng = random.Random(args.seed)

    day_start = datetime.fromisoformat(f"{args.date}T08:00:00+00:00")
    run_id = f"run_gen_{args.date.replace('-', '')}_{uuid4().hex[:6]}"
    session_id = f"session_gen_{uuid4().hex[:6]}"

    qb = QuantBuildEmitter.from_base_path(
        base_path=output_path,
        source_component="quantbuild_generator",
        environment=args.environment,
        run_id=run_id,
        session_id=session_id,
    )
    qbr = QuantBridgeEmitter.from_base_path(
        base_path=output_path,
        source_component="quantbridge_generator",
        environment=args.environment,
        run_id=run_id,
        session_id=session_id,
    )

    traces = max(1, int(args.traces))
    ratios = {
        "happy": max(0.0, float(args.happy_ratio)),
        "blocked": max(0.0, float(args.blocked_ratio)),
        "rejected": max(0.0, float(args.rejected_ratio)),
        "partial_fill": max(0.0, float(args.partial_fill_ratio)),
        "governance_pause": max(0.0, float(args.governance_ratio)),
        "failsafe_pause": max(0.0, float(args.failsafe_ratio)),
        "adaptive_mode": max(0.0, float(args.adaptive_ratio)),
    }
    ratio_sum = sum(ratios.values())
    if ratio_sum <= 0:
        ratios["happy"] = 1.0
        ratio_sum = 1.0
    normalized = {key: value / ratio_sum for key, value in ratios.items()}

    thresholds: list[tuple[str, float]] = []
    running = 0.0
    for key, value in normalized.items():
        running += value
        thresholds.append((key, running))

    counts = {
        "happy": 0,
        "blocked": 0,
        "rejected": 0,
        "partial_fill": 0,
        "governance_pause": 0,
        "failsafe_pause": 0,
        "adaptive_mode": 0,
    }
    for idx in range(traces):
        base_dt = day_start + timedelta(minutes=idx)
        ids = _mk_ids("sample", idx)
        roll = rng.random()
        scenario = "happy"
        for name, threshold in thresholds:
            if roll <= threshold:
                scenario = name
                break

        if scenario == "happy":
            _emit_happy(qb, qbr, ids, base_dt, args.account_id, args.strategy_id, args.symbol)
        elif scenario == "blocked":
            _emit_blocked(qb, ids, base_dt, args.account_id, args.strategy_id, args.symbol)
        elif scenario == "rejected":
            _emit_rejected(qb, qbr, ids, base_dt, args.account_id, args.strategy_id, args.symbol)
        elif scenario == "partial_fill":
            _emit_partial_fill(qb, qbr, ids, base_dt, args.account_id, args.strategy_id, args.symbol)
        elif scenario == "governance_pause":
            _emit_governance_pause(
                qb, qbr, ids, base_dt, args.account_id, args.strategy_id, args.symbol
            )
        elif scenario == "failsafe_pause":
            _emit_failsafe_pause(
                qb, qbr, ids, base_dt, args.account_id, args.strategy_id, args.symbol
            )
        elif scenario == "adaptive_mode":
            _emit_adaptive_mode(qb, ids, base_dt, args.account_id, args.strategy_id, args.symbol)
        counts[scenario] += 1

    if args.include_session_restart_probe:
        _emit_session_restart_probe(
            output_path=output_path,
            environment=args.environment,
            run_id=run_id,
            session_id=session_id,
            base_dt=day_start + timedelta(minutes=traces + 1),
            account_id=args.account_id,
            strategy_id=args.strategy_id,
            symbol=args.symbol,
        )
        counts["adaptive_mode"] += 0  # explicit no-op to keep deterministic keys

    anomaly_stats = {"duplicates_injected": 0, "missing_trace_injected": 0, "out_of_order_injected": 0}
    if args.inject_anomalies:
        anomaly_stats = _inject_anomalies(output_path=output_path, date=args.date)

    print("SAMPLE DAY GENERATED")
    print(f"output_path={output_path}")
    print(f"date={args.date}")
    print(f"run_id={run_id}")
    print(f"session_id={session_id}")
    print(f"traces_total={traces}")
    print(
        "scenario_counts="
        + ",".join(
            f"{key}:{counts[key]}"
            for key in [
                "happy",
                "blocked",
                "rejected",
                "partial_fill",
                "governance_pause",
                "failsafe_pause",
                "adaptive_mode",
            ]
        )
    )
    if args.include_session_restart_probe:
        print("session_restart_probe=enabled")
    if args.inject_anomalies:
        print(
            "anomalies_injected="
            + ",".join(f"{k}:{v}" for k, v in anomaly_stats.items())
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

