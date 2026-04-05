"""QuantLog event validation."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from quantlog.events.io import RawEventLine, discover_jsonl_files, iter_jsonl_file
from quantlog.events.schema import (
    ALLOWED_ENVIRONMENTS,
    ALLOWED_SEVERITIES,
    ALLOWED_SOURCE_SYSTEMS,
    EVENT_PAYLOAD_REQUIRED,
    NO_ACTION_REASONS_ALLOWED,
    REQUIRED_ENVELOPE_FIELDS,
    RISK_GUARD_DECISIONS,
    TRADE_ACTION_DECISIONS,
)


@dataclass(slots=True, frozen=True)
class ValidationIssue:
    level: str  # error|warn
    path: Path
    line_number: int
    message: str


@dataclass(slots=True, frozen=True)
class ValidationReport:
    files_scanned: int
    lines_scanned: int
    events_valid: int
    issues: list[ValidationIssue]


def validation_issue_code(message: str) -> str:
    """Stable bucket for aggregating validation messages (ops / CI summaries)."""
    if ": " in message:
        return message.split(": ", 1)[0].strip()
    return message


def aggregate_validation_issue_codes(issues: list[ValidationIssue]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for issue in issues:
        counts[validation_issue_code(issue.message)] += 1
    return dict(counts)


def _is_utc_iso8601(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt.tzinfo is not None
    except ValueError:
        return False


def _validate_uuid(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    try:
        UUID(value)
        return True
    except ValueError:
        return False


def validate_raw_event(raw_line: RawEventLine) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    if raw_line.parsed is None:
        issues.append(
            ValidationIssue(
                level="error",
                path=raw_line.path,
                line_number=raw_line.line_number,
                message=f"invalid_json: {raw_line.parse_error}",
            )
        )
        return issues

    event = raw_line.parsed
    missing = REQUIRED_ENVELOPE_FIELDS - set(event.keys())
    for field_name in sorted(missing):
        issues.append(
            ValidationIssue(
                level="error",
                path=raw_line.path,
                line_number=raw_line.line_number,
                message=f"missing_required_field: {field_name}",
            )
        )

    if "event_id" in event and not _validate_uuid(event["event_id"]):
        issues.append(
            ValidationIssue(
                level="error",
                path=raw_line.path,
                line_number=raw_line.line_number,
                message="invalid_event_id_uuid",
            )
        )

    if "timestamp_utc" in event and not _is_utc_iso8601(event["timestamp_utc"]):
        issues.append(
            ValidationIssue(
                level="error",
                path=raw_line.path,
                line_number=raw_line.line_number,
                message="invalid_timestamp_utc",
            )
        )

    if "ingested_at_utc" in event and not _is_utc_iso8601(event["ingested_at_utc"]):
        issues.append(
            ValidationIssue(
                level="error",
                path=raw_line.path,
                line_number=raw_line.line_number,
                message="invalid_ingested_at_utc",
            )
        )
    elif "timestamp_utc" in event and "ingested_at_utc" in event:
        ts_dt = datetime.fromisoformat(str(event["timestamp_utc"]).replace("Z", "+00:00"))
        ingest_dt = datetime.fromisoformat(str(event["ingested_at_utc"]).replace("Z", "+00:00"))
        if ingest_dt < ts_dt:
            issues.append(
                ValidationIssue(
                    level="warn",
                    path=raw_line.path,
                    line_number=raw_line.line_number,
                    message="ingested_before_event_timestamp",
                )
            )

    source_system = event.get("source_system")
    if source_system is not None and source_system not in ALLOWED_SOURCE_SYSTEMS:
        issues.append(
            ValidationIssue(
                level="error",
                path=raw_line.path,
                line_number=raw_line.line_number,
                message=f"invalid_source_system: {source_system}",
            )
        )

    severity = event.get("severity")
    if severity is not None and severity not in ALLOWED_SEVERITIES:
        issues.append(
            ValidationIssue(
                level="error",
                path=raw_line.path,
                line_number=raw_line.line_number,
                message=f"invalid_severity: {severity}",
            )
        )

    environment = event.get("environment")
    if environment is not None and environment not in ALLOWED_ENVIRONMENTS:
        issues.append(
            ValidationIssue(
                level="error",
                path=raw_line.path,
                line_number=raw_line.line_number,
                message=f"invalid_environment: {environment}",
            )
        )

    source_seq = event.get("source_seq")
    if source_seq is not None and (not isinstance(source_seq, int) or source_seq < 1):
        issues.append(
            ValidationIssue(
                level="error",
                path=raw_line.path,
                line_number=raw_line.line_number,
                message="invalid_source_seq",
            )
        )

    # Required correlation fields: key may be present with JSON null — still invalid.
    for text_field in ("run_id", "session_id", "trace_id"):
        if text_field not in event:
            continue
        value = event[text_field]
        if not isinstance(value, str) or not value.strip():
            issues.append(
                ValidationIssue(
                    level="error",
                    path=raw_line.path,
                    line_number=raw_line.line_number,
                    message=f"invalid_{text_field}",
                )
            )

    payload = event.get("payload")
    if payload is not None and not isinstance(payload, dict):
        issues.append(
            ValidationIssue(
                level="error",
                path=raw_line.path,
                line_number=raw_line.line_number,
                message="payload_not_object",
            )
        )
        return issues

    event_type = event.get("event_type")
    required_payload = EVENT_PAYLOAD_REQUIRED.get(event_type)
    if required_payload is None:
        issues.append(
            ValidationIssue(
                level="warn",
                path=raw_line.path,
                line_number=raw_line.line_number,
                message=f"unknown_event_type: {event_type}",
            )
        )
    elif isinstance(payload, dict):
        missing_payload_fields = required_payload - set(payload.keys())
        for field_name in sorted(missing_payload_fields):
            issues.append(
                ValidationIssue(
                    level="error",
                    path=raw_line.path,
                    line_number=raw_line.line_number,
                    message=f"missing_payload_field[{event_type}]: {field_name}",
                )
            )

    if event_type == "trade_action" and isinstance(payload, dict):
        decision = str(payload.get("decision", "")).upper()
        if decision not in TRADE_ACTION_DECISIONS:
            issues.append(
                ValidationIssue(
                    level="error",
                    path=raw_line.path,
                    line_number=raw_line.line_number,
                    message=f"invalid_trade_action_decision: {decision}",
                )
            )
        elif decision == "NO_ACTION" and "reason" in payload:
            reason = payload["reason"]
            if not isinstance(reason, str) or reason not in NO_ACTION_REASONS_ALLOWED:
                issues.append(
                    ValidationIssue(
                        level="error",
                        path=raw_line.path,
                        line_number=raw_line.line_number,
                        message=f"invalid_no_action_reason: {reason!r}",
                    )
                )

    if event_type == "risk_guard_decision" and isinstance(payload, dict):
        decision = str(payload.get("decision", "")).upper()
        if decision not in RISK_GUARD_DECISIONS:
            issues.append(
                ValidationIssue(
                    level="error",
                    path=raw_line.path,
                    line_number=raw_line.line_number,
                    message=f"invalid_risk_guard_decision: {decision}",
                )
            )

    if event_type in {"order_submitted", "order_filled", "order_rejected"} and not event.get(
        "order_ref"
    ):
        issues.append(
            ValidationIssue(
                level="warn",
                path=raw_line.path,
                line_number=raw_line.line_number,
                message="execution_event_missing_order_ref",
            )
        )

    if event_type == "governance_state_changed" and not event.get("account_id"):
        issues.append(
            ValidationIssue(
                level="warn",
                path=raw_line.path,
                line_number=raw_line.line_number,
                message="governance_event_missing_account_id",
            )
        )

    return issues


def _monotonic_source_seq_issues(
    raw_line: RawEventLine, seq_last: dict[str, int]
) -> list[ValidationIssue]:
    """Enforce strictly increasing source_seq per emitter stream within one JSONL file."""
    issues: list[ValidationIssue] = []
    if raw_line.parsed is None:
        return issues
    event = raw_line.parsed
    sq = event.get("source_seq")
    if not isinstance(sq, int) or sq < 1:
        return issues
    run_id = event.get("run_id")
    session_id = event.get("session_id")
    source_system = event.get("source_system")
    source_component = event.get("source_component")
    if not (
        isinstance(run_id, str)
        and run_id.strip()
        and isinstance(session_id, str)
        and session_id.strip()
        and isinstance(source_system, str)
        and source_system.strip()
        and isinstance(source_component, str)
        and source_component.strip()
    ):
        return issues
    key = f"{source_system.strip()}|{source_component.strip()}|{run_id.strip()}|{session_id.strip()}"
    prev = seq_last.get(key)
    if prev is not None and sq <= prev:
        issues.append(
            ValidationIssue(
                level="error",
                path=raw_line.path,
                line_number=raw_line.line_number,
                message=f"source_seq_not_monotonic: stream={key!r} prev={prev} current={sq}",
            )
        )
    else:
        seq_last[key] = sq
    return issues


def validate_path(path: Path) -> ValidationReport:
    jsonl_files = discover_jsonl_files(path)
    issues: list[ValidationIssue] = []
    lines_scanned = 0
    events_valid = 0

    for jsonl_path in jsonl_files:
        seq_last: dict[str, int] = {}
        for raw_line in iter_jsonl_file(jsonl_path):
            lines_scanned += 1
            event_issues = validate_raw_event(raw_line)
            mono_issues = _monotonic_source_seq_issues(raw_line, seq_last)
            combined = event_issues + mono_issues
            issues.extend(combined)
            if not any(issue.level == "error" for issue in combined):
                events_valid += 1

    return ValidationReport(
        files_scanned=len(jsonl_files),
        lines_scanned=lines_scanned,
        events_valid=events_valid,
        issues=issues,
    )

