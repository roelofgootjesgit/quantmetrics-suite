"""QuantLog CLI: validate, replay, summarize."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from quantlog.ingest.health import detect_audit_gaps, emit_audit_gap_events
from quantlog.quality.service import score_run
from quantlog.replay.service import replay_trace
from quantlog.summarize.service import summarize_path
from quantlog.events.schema import (
    ALLOWED_ENVIRONMENTS,
    ALLOWED_SEVERITIES,
    ALLOWED_SOURCE_SYSTEMS,
    COMBO_MODULE_LABELS,
    EVENT_PAYLOAD_REQUIRED,
    GATE_SUMMARY_GATE_KEYS,
    GATE_SUMMARY_STATUSES,
    NO_ACTION_REASONS_ALLOWED,
    NO_ACTION_REASONS_CORE,
    NO_ACTION_REASONS_EXTENDED,
    REQUIRED_ENVELOPE_FIELDS,
    RISK_GUARD_DECISIONS,
    SIGNAL_EVALUATED_OPTIONAL_PAYLOAD_KEYS,
    TRADE_ACTION_DECISIONS,
    TRADE_EXECUTED_DIRECTIONS,
)
from quantlog.validate.validator import aggregate_validation_issue_codes, validate_path


def _print_json(data: dict[str, Any]) -> None:
    print(json.dumps(data, indent=2, ensure_ascii=True))


def cmd_validate_events(args: argparse.Namespace) -> int:
    report = validate_path(Path(args.path))
    errors = [issue for issue in report.issues if issue.level == "error"]
    warnings = [issue for issue in report.issues if issue.level == "warn"]
    output = {
        "files_scanned": report.files_scanned,
        "lines_scanned": report.lines_scanned,
        "events_valid": report.events_valid,
        "issues_total": len(report.issues),
        "errors_total": len(errors),
        "warnings_total": len(warnings),
        "errors_by_code": aggregate_validation_issue_codes(errors),
        "warnings_by_code": aggregate_validation_issue_codes(warnings),
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
        "trade_action_by_decision": summary.trade_action_by_decision,
        "no_action_by_reason": summary.no_action_by_reason,
        "risk_guard_by_decision": summary.risk_guard_by_decision,
        "risk_guard_blocks_by_guard": summary.risk_guard_blocks_by_guard,
        "signal_filtered_by_reason": summary.signal_filtered_by_reason,
        "by_severity": summary.by_severity,
        "by_source_system": summary.by_source_system,
        "by_source_component": summary.by_source_component,
        "by_environment": summary.by_environment,
        "non_contract_event_types": summary.non_contract_event_types,
        "count_unique_run_ids": summary.count_unique_run_ids,
        "count_unique_session_ids": summary.count_unique_session_ids,
        "count_unique_trace_ids": summary.count_unique_trace_ids,
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


def cmd_score_run(args: argparse.Namespace) -> int:
    report = score_run(
        path=Path(args.path),
        max_gap_seconds=float(args.max_gap_seconds),
        pass_threshold=int(args.pass_threshold),
    )
    output = {
        "score": report.score,
        "grade": report.grade,
        "pass_threshold": report.pass_threshold,
        "passed": report.passed,
        "events_total": report.events_total,
        "invalid_json_lines": report.invalid_json_lines,
        "errors_total": report.errors_total,
        "warnings_total": report.warnings_total,
        "duplicate_event_ids": report.duplicate_event_ids,
        "out_of_order_events": report.out_of_order_events,
        "missing_trace_ids": report.missing_trace_ids,
        "missing_order_ref_execution": report.missing_order_ref_execution,
        "audit_gaps": report.audit_gaps,
        "penalty_breakdown": report.penalty_breakdown,
        "trades_attempted": report.trades_attempted,
        "trades_filled": report.trades_filled,
        "blocks_total": report.blocks_total,
        "no_action_by_reason": report.no_action_by_reason,
        "trade_action_by_decision": report.trade_action_by_decision,
        "risk_guard_by_decision": report.risk_guard_by_decision,
        "risk_guard_blocks_by_guard": report.risk_guard_blocks_by_guard,
        "by_event_type": report.by_event_type,
        "by_severity": report.by_severity,
        "by_source_system": report.by_source_system,
        "by_source_component": report.by_source_component,
        "by_environment": report.by_environment,
        "non_contract_event_types": report.non_contract_event_types,
        "count_unique_run_ids": report.count_unique_run_ids,
        "count_unique_session_ids": report.count_unique_session_ids,
        "count_unique_trace_ids": report.count_unique_trace_ids,
    }
    _print_json(output)
    return 0 if report.passed else 4


def cmd_list_no_action_reasons(_args: argparse.Namespace) -> int:
    """Emit canonical NO_ACTION reason strings (for emitter / QuantBuild alignment)."""
    _print_json(
        {
            "core": sorted(NO_ACTION_REASONS_CORE),
            "extended": sorted(NO_ACTION_REASONS_EXTENDED),
            "all_allowed": sorted(NO_ACTION_REASONS_ALLOWED),
        }
    )
    return 0


def cmd_list_event_types(_args: argparse.Namespace) -> int:
    """Emit v1 event types and required payload keys (schema alignment)."""
    contracts = {et: sorted(fields) for et, fields in sorted(EVENT_PAYLOAD_REQUIRED.items())}
    _print_json(
        {"event_types": sorted(EVENT_PAYLOAD_REQUIRED.keys()), "payload_contracts": contracts}
    )
    return 0


def cmd_list_envelope_schema(_args: argparse.Namespace) -> int:
    """Emit envelope field names and allowed enum values (emitter alignment)."""
    _print_json(
        {
            "required_envelope_fields": sorted(REQUIRED_ENVELOPE_FIELDS),
            "allowed_source_systems": sorted(ALLOWED_SOURCE_SYSTEMS),
            "allowed_severities": sorted(ALLOWED_SEVERITIES),
            "allowed_environments": sorted(ALLOWED_ENVIRONMENTS),
            "trade_action_decisions": sorted(TRADE_ACTION_DECISIONS),
            "risk_guard_decisions": sorted(RISK_GUARD_DECISIONS),
            "trade_executed_directions": sorted(TRADE_EXECUTED_DIRECTIONS),
        }
    )
    return 0


def cmd_export_v1_schema(_args: argparse.Namespace) -> int:
    """Single JSON bundle: envelope enums, event payload contracts, NO_ACTION reasons."""
    contracts = {et: sorted(fields) for et, fields in sorted(EVENT_PAYLOAD_REQUIRED.items())}
    _print_json(
        {
            "schema_id": "quantlog_v1",
            "envelope": {
                "required_fields": sorted(REQUIRED_ENVELOPE_FIELDS),
                "allowed_source_systems": sorted(ALLOWED_SOURCE_SYSTEMS),
                "allowed_severities": sorted(ALLOWED_SEVERITIES),
                "allowed_environments": sorted(ALLOWED_ENVIRONMENTS),
                "trade_action_decisions": sorted(TRADE_ACTION_DECISIONS),
                "risk_guard_decisions": sorted(RISK_GUARD_DECISIONS),
                "trade_executed_directions": sorted(TRADE_EXECUTED_DIRECTIONS),
            },
            "event_types": {
                "names": sorted(EVENT_PAYLOAD_REQUIRED.keys()),
                "payload_contracts": contracts,
            },
            "no_action_reasons": {
                "core": sorted(NO_ACTION_REASONS_CORE),
                "extended": sorted(NO_ACTION_REASONS_EXTENDED),
                "all_allowed": sorted(NO_ACTION_REASONS_ALLOWED),
            },
            "signal_evaluated_optional": {
                "payload_keys": list(SIGNAL_EVALUATED_OPTIONAL_PAYLOAD_KEYS),
                "gate_summary_gate_keys": sorted(GATE_SUMMARY_GATE_KEYS),
                "gate_summary_statuses": sorted(GATE_SUMMARY_STATUSES),
                "combo_module_labels": sorted(COMBO_MODULE_LABELS),
            },
        }
    )
    return 0


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

    score_parser = subparsers.add_parser(
        "score-run", help="Compute run quality scorecard"
    )
    score_parser.add_argument("--path", required=True, help="Path to JSONL file or folder")
    score_parser.add_argument(
        "--max-gap-seconds",
        default=300,
        type=float,
        help="Gap threshold used by quality score",
    )
    score_parser.add_argument(
        "--pass-threshold",
        default=95,
        type=int,
        help="Minimum score for pass",
    )
    score_parser.set_defaults(func=cmd_score_run)

    reasons_parser = subparsers.add_parser(
        "list-no-action-reasons",
        help="Print canonical trade_action NO_ACTION reason strings (JSON)",
    )
    reasons_parser.set_defaults(func=cmd_list_no_action_reasons)

    types_parser = subparsers.add_parser(
        "list-event-types",
        help="Print v1 event_type names and required payload fields (JSON)",
    )
    types_parser.set_defaults(func=cmd_list_event_types)

    env_parser = subparsers.add_parser(
        "list-envelope-schema",
        help="Print required envelope fields and allowed severity/environment/source_system (JSON)",
    )
    env_parser.set_defaults(func=cmd_list_envelope_schema)

    export_parser = subparsers.add_parser(
        "export-v1-schema",
        help="Print full v1 schema bundle (envelope + event types + NO_ACTION reasons) as one JSON",
    )
    export_parser.set_defaults(func=cmd_export_v1_schema)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())

