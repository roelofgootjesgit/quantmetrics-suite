"""Generate a synthetic QuantLog event day for replay/metrics testing."""

from __future__ import annotations

import argparse
import random
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from quantlog.ingest.adapters import QuantBridgeEmitter, QuantBuildEmitter


@dataclass(slots=True, frozen=True)
class TraceIds:
    trace_id: str
    order_ref: str
    position_id: str


def _mk_ids(prefix: str, idx: int) -> TraceIds:
    suffix = uuid4().hex[:8]
    return TraceIds(
        trace_id=f"trace_{prefix}_{idx}_{suffix}",
        order_ref=f"ord_{prefix}_{idx}_{suffix}",
        position_id=f"pos_{prefix}_{idx}_{suffix}",
    )


def _fmt(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat().replace("+00:00", "Z")


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
        account_id=account_id,
        strategy_id=strategy_id,
        symbol=symbol,
        timestamp_utc=_fmt(base_dt + timedelta(seconds=0)),
        payload={"signal_type": "ict_sweep", "signal_direction": "LONG", "confidence": 0.65},
    )
    qb.emit(
        event_type="risk_guard_decision",
        trace_id=ids.trace_id,
        account_id=account_id,
        strategy_id=strategy_id,
        symbol=symbol,
        timestamp_utc=_fmt(base_dt + timedelta(seconds=1)),
        payload={"guard_name": "spread_guard", "decision": "ALLOW", "reason": "spread_ok"},
    )
    qb.emit(
        event_type="trade_action",
        trace_id=ids.trace_id,
        account_id=account_id,
        strategy_id=strategy_id,
        symbol=symbol,
        timestamp_utc=_fmt(base_dt + timedelta(seconds=2)),
        payload={"decision": "ENTER", "reason": "all_guards_passed", "side": "BUY"},
    )
    qbr.emit(
        event_type="order_submitted",
        trace_id=ids.trace_id,
        order_ref=ids.order_ref,
        account_id=account_id,
        strategy_id=strategy_id,
        symbol=symbol,
        timestamp_utc=_fmt(base_dt + timedelta(seconds=3)),
        payload={"order_ref": ids.order_ref, "side": "BUY", "volume": 0.5},
    )
    qbr.emit(
        event_type="order_filled",
        trace_id=ids.trace_id,
        order_ref=ids.order_ref,
        position_id=ids.position_id,
        account_id=account_id,
        strategy_id=strategy_id,
        symbol=symbol,
        timestamp_utc=_fmt(base_dt + timedelta(seconds=4)),
        payload={"order_ref": ids.order_ref, "fill_price": 2350.0, "slippage": 0.08},
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
        account_id=account_id,
        strategy_id=strategy_id,
        symbol=symbol,
        timestamp_utc=_fmt(base_dt + timedelta(seconds=0)),
        payload={"signal_type": "ict_sweep", "signal_direction": "SHORT", "confidence": 0.57},
    )
    qb.emit(
        event_type="risk_guard_decision",
        trace_id=ids.trace_id,
        account_id=account_id,
        strategy_id=strategy_id,
        symbol=symbol,
        timestamp_utc=_fmt(base_dt + timedelta(seconds=1)),
        payload={"guard_name": "spread_guard", "decision": "BLOCK", "reason": "spread_too_wide"},
    )
    qb.emit(
        event_type="trade_action",
        trace_id=ids.trace_id,
        account_id=account_id,
        strategy_id=strategy_id,
        symbol=symbol,
        timestamp_utc=_fmt(base_dt + timedelta(seconds=2)),
        payload={"decision": "NO_ACTION", "reason": "blocked_by_guard", "side": "SELL"},
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
        account_id=account_id,
        strategy_id=strategy_id,
        symbol=symbol,
        timestamp_utc=_fmt(base_dt + timedelta(seconds=0)),
        payload={"signal_type": "ict_sweep", "signal_direction": "LONG", "confidence": 0.6},
    )
    qb.emit(
        event_type="risk_guard_decision",
        trace_id=ids.trace_id,
        account_id=account_id,
        strategy_id=strategy_id,
        symbol=symbol,
        timestamp_utc=_fmt(base_dt + timedelta(seconds=1)),
        payload={"guard_name": "spread_guard", "decision": "ALLOW", "reason": "spread_ok"},
    )
    qb.emit(
        event_type="trade_action",
        trace_id=ids.trace_id,
        account_id=account_id,
        strategy_id=strategy_id,
        symbol=symbol,
        timestamp_utc=_fmt(base_dt + timedelta(seconds=2)),
        payload={"decision": "ENTER", "reason": "entry_allowed", "side": "BUY"},
    )
    qbr.emit(
        event_type="order_submitted",
        trace_id=ids.trace_id,
        order_ref=ids.order_ref,
        account_id=account_id,
        strategy_id=strategy_id,
        symbol=symbol,
        timestamp_utc=_fmt(base_dt + timedelta(seconds=3)),
        payload={"order_ref": ids.order_ref, "side": "BUY", "volume": 0.5},
    )
    qbr.emit(
        event_type="order_rejected",
        trace_id=ids.trace_id,
        order_ref=ids.order_ref,
        account_id=account_id,
        strategy_id=strategy_id,
        symbol=symbol,
        timestamp_utc=_fmt(base_dt + timedelta(seconds=4)),
        payload={"order_ref": ids.order_ref, "reason": "insufficient_margin"},
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate a sample QuantLog event day")
    parser.add_argument("--output-path", default="data/events/generated", help="Base output event path")
    parser.add_argument("--date", default=datetime.now(tz=UTC).strftime("%Y-%m-%d"), help="UTC date YYYY-MM-DD")
    parser.add_argument("--traces", type=int, default=20, help="Total traces to generate")
    parser.add_argument("--happy-ratio", type=float, default=0.6, help="Happy path ratio")
    parser.add_argument("--blocked-ratio", type=float, default=0.25, help="Blocked path ratio")
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
    happy_ratio = max(0.0, min(1.0, float(args.happy_ratio)))
    blocked_ratio = max(0.0, min(1.0, float(args.blocked_ratio)))
    rejected_ratio = max(0.0, 1.0 - happy_ratio - blocked_ratio)

    counts = {"happy": 0, "blocked": 0, "rejected": 0}
    for idx in range(traces):
        base_dt = day_start + timedelta(minutes=idx)
        ids = _mk_ids("sample", idx)
        roll = rng.random()
        if roll < happy_ratio:
            _emit_happy(
                qb, qbr, ids, base_dt, args.account_id, args.strategy_id, args.symbol
            )
            counts["happy"] += 1
        elif roll < happy_ratio + blocked_ratio:
            _emit_blocked(qb, ids, base_dt, args.account_id, args.strategy_id, args.symbol)
            counts["blocked"] += 1
        else:
            _emit_rejected(
                qb, qbr, ids, base_dt, args.account_id, args.strategy_id, args.symbol
            )
            counts["rejected"] += 1

    print("SAMPLE DAY GENERATED")
    print(f"output_path={output_path}")
    print(f"date={args.date}")
    print(f"run_id={run_id}")
    print(f"session_id={session_id}")
    print(
        f"traces_total={traces} happy={counts['happy']} blocked={counts['blocked']} rejected={counts['rejected']} rejected_ratio={rejected_ratio:.2f}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

