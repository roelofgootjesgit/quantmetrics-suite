"""QuantLog CLI: validate, replay, summarize."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from quantlog.ingest.health import detect_audit_gaps, emit_audit_gap_events
from quantlog.replay.service import replay_trace
from quantlog.summarize.service import summarize_path
from quantlog.validate.validator import validate_path


def _print_json(data: dict[str, Any]) -> None:
    print(json.dumps(data, indent=2, ensure_ascii=True))


def cmd_validate_events(args: argparse.Namespace) -> int:
    report = validate_path(Path(args.path))
    output = {
        "files_scanned": report.files_scanned,
        "lines_scanned": report.lines_scanned,
        "events_valid": report.events_valid,
        "issues_total": len(report.issues),
        "errors_total": sum(1 for issue in report.issues if issue.level == "error"),
        "warnings_total": sum(1 for issue in report.issues if issue.level == "warn"),
        "issues": [
            {
                "level": issue.level,
                "path": str(issue.path),
                "line_number": issue.line_number,
                "message": issue.message,
            }
            for issue in report.issues
        ],
    }
    _print_json(output)
    return 1 if output["errors_total"] > 0 else 0


def cmd_replay_trace(args: argparse.Namespace) -> int:
    items = replay_trace(Path(args.path), args.trace_id)
    output = {
        "trace_id": args.trace_id,
        "events_found": len(items),
        "timeline": [
            {
                "timestamp_utc": item.timestamp_utc,
                "source_seq": item.source_seq,
                "source_system": item.source_system,
                "event_type": item.event_type,
                "summary": item.summary,
                "payload": item.payload,
            }
            for item in items
        ],
    }
    _print_json(output)
    return 0 if items else 2


def cmd_summarize_day(args: argparse.Namespace) -> int:
    summary = summarize_path(Path(args.path))
    output = {
        "files_scanned": summary.files_scanned,
        "events_total": summary.events_total,
        "invalid_json_lines": summary.invalid_json_lines,
        "by_event_type": summary.by_event_type,
        "trades_attempted": summary.trades_attempted,
        "trades_filled": summary.trades_filled,
        "blocks_total": summary.blocks_total,
        "broker_rejects": summary.broker_rejects,
        "failsafe_pauses": summary.failsafe_pauses,
        "audit_gaps_detected": summary.audit_gaps_detected,
        "avg_slippage": summary.avg_slippage,
        "median_slippage": summary.median_slippage,
    }
    _print_json(output)
    return 0


def cmd_check_ingest_health(args: argparse.Namespace) -> int:
    path = Path(args.path)
    gaps = detect_audit_gaps(path=path, max_gap_seconds=float(args.max_gap_seconds))
    emitted_count = 0
    if args.emit_audit_gap and gaps:
        emitted = emit_audit_gap_events(base_path=path, gaps=gaps)
        emitted_count = len(emitted)

    output = {
        "path": str(path),
        "max_gap_seconds": float(args.max_gap_seconds),
        "gaps_found": len(gaps),
        "emitted_audit_gap_events": emitted_count,
        "gaps": [
            {
                "source_system": gap.source_system,
                "previous_ingested_at_utc": gap.previous_ingested_at_utc,
                "current_ingested_at_utc": gap.current_ingested_at_utc,
                "gap_seconds": gap.gap_seconds,
            }
            for gap in gaps
        ],
    }
    _print_json(output)
    return 0 if not gaps else 3


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="QuantLog v1 CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate_parser = subparsers.add_parser(
        "validate-events", help="Validate QuantLog JSONL events"
    )
    validate_parser.add_argument("--path", required=True, help="Path to JSONL file or folder")
    validate_parser.set_defaults(func=cmd_validate_events)

    replay_parser = subparsers.add_parser(
        "replay-trace", help="Replay timeline for a trace_id"
    )
    replay_parser.add_argument("--path", required=True, help="Path to JSONL file or folder")
    replay_parser.add_argument("--trace-id", required=True, help="Trace id to replay")
    replay_parser.set_defaults(func=cmd_replay_trace)

    summary_parser = subparsers.add_parser("summarize-day", help="Summarize event set")
    summary_parser.add_argument("--path", required=True, help="Path to JSONL file or folder")
    summary_parser.set_defaults(func=cmd_summarize_day)

    health_parser = subparsers.add_parser(
        "check-ingest-health", help="Detect ingest audit gaps by ingested_at_utc"
    )
    health_parser.add_argument("--path", required=True, help="Path to JSONL file or folder")
    health_parser.add_argument(
        "--max-gap-seconds",
        default=120,
        type=float,
        help="Max allowed ingest gap in seconds before raising audit gap",
    )
    health_parser.add_argument(
        "--emit-audit-gap",
        action="store_true",
        help="Emit audit_gap_detected events into the same event store path",
    )
    health_parser.set_defaults(func=cmd_check_ingest_health)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())

