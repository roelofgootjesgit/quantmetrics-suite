"""Run quality scorecard service."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from quantlog.events.io import discover_jsonl_files, iter_jsonl_file
from quantlog.ingest.health import detect_audit_gaps
from quantlog.summarize.service import summarize_path
from quantlog.validate.validator import validate_path


@dataclass(slots=True, frozen=True)
class RunQualityReport:
    score: int
    grade: str
    pass_threshold: int
    passed: bool
    events_total: int
    invalid_json_lines: int
    errors_total: int
    warnings_total: int
    duplicate_event_ids: int
    out_of_order_events: int
    missing_trace_ids: int
    missing_order_ref_execution: int
    audit_gaps: int
    penalty_breakdown: dict[str, int]
    trades_attempted: int
    trades_filled: int
    blocks_total: int
    no_action_by_reason: dict[str, int]
    trade_action_by_decision: dict[str, int]
    risk_guard_by_decision: dict[str, int]
    risk_guard_blocks_by_guard: dict[str, int]
    by_event_type: dict[str, int]
    by_severity: dict[str, int]
    by_source_system: dict[str, int]
    by_source_component: dict[str, int]
    by_environment: dict[str, int]
    non_contract_event_types: dict[str, int]
    count_unique_run_ids: int
    count_unique_session_ids: int
    count_unique_trace_ids: int


def _safe_dt(value: Any) -> datetime:
    if not isinstance(value, str):
        return datetime.min
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return datetime.min


def _calc_grade(score: int) -> str:
    if score >= 98:
        return "A+"
    if score >= 95:
        return "A"
    if score >= 90:
        return "B"
    if score >= 80:
        return "C"
    return "D"


def _scan_event_integrity(path: Path) -> tuple[int, int, int, int]:
    seen_event_ids: set[str] = set()
    duplicate_event_ids = 0
    out_of_order = 0
    missing_trace_ids = 0
    missing_order_ref_execution = 0
    stream_last_key: dict[str, tuple[datetime, int]] = {}

    for jsonl_path in discover_jsonl_files(path):
        for raw_line in iter_jsonl_file(jsonl_path):
            if raw_line.parsed is None:
                continue
            event = raw_line.parsed
            event_type = str(event.get("event_type", ""))

            event_id = event.get("event_id")
            if isinstance(event_id, str):
                if event_id in seen_event_ids:
                    duplicate_event_ids += 1
                else:
                    seen_event_ids.add(event_id)

            source_system = str(event.get("source_system", "unknown"))
            source_component = str(event.get("source_component", "unknown"))
            run_id = str(event.get("run_id", "unknown"))
            session_id = str(event.get("session_id", "unknown"))
            stream_key = f"{source_system}|{source_component}|{run_id}|{session_id}"

            ts = _safe_dt(event.get("timestamp_utc"))
            source_seq = event.get("source_seq")
            seq = source_seq if isinstance(source_seq, int) else 0
            current = (ts, seq)
            previous = stream_last_key.get(stream_key)
            if previous is not None and current < previous:
                out_of_order += 1
            stream_last_key[stream_key] = current

            trace_id = event.get("trace_id")
            if not isinstance(trace_id, str) or not trace_id.strip():
                missing_trace_ids += 1

            if event_type in {"order_submitted", "order_filled", "order_rejected", "trade_executed"}:
                order_ref = event.get("order_ref")
                if not isinstance(order_ref, str) or not order_ref.strip():
                    missing_order_ref_execution += 1

    return duplicate_event_ids, out_of_order, missing_trace_ids, missing_order_ref_execution


def score_run(path: Path, max_gap_seconds: float = 300.0, pass_threshold: int = 95) -> RunQualityReport:
    validation = validate_path(path)
    summary = summarize_path(path)
    gaps = detect_audit_gaps(path=path, max_gap_seconds=max_gap_seconds)
    (
        duplicate_event_ids,
        out_of_order_events,
        missing_trace_ids,
        missing_order_ref_execution,
    ) = _scan_event_integrity(path)

    errors_total = sum(1 for issue in validation.issues if issue.level == "error")
    warnings_total = sum(1 for issue in validation.issues if issue.level == "warn")

    non_contract_total = sum(summary.non_contract_event_types.values())
    penalties = {
        "errors": min(errors_total * 25, 60),
        "warnings": min(warnings_total * 2, 20),
        "invalid_json": min(summary.invalid_json_lines * 5, 25),
        "audit_gaps": min(len(gaps) * 15, 30),
        "duplicate_event_ids": min(duplicate_event_ids * 5, 20),
        "out_of_order_events": min(out_of_order_events * 2, 20),
        "missing_trace_ids": min(missing_trace_ids * 20, 60),
        "missing_order_ref_execution": min(missing_order_ref_execution * 10, 30),
        "non_contract_event_types": min(non_contract_total * 3, 15),
    }
    total_penalty = sum(penalties.values())
    score = max(0, 100 - total_penalty)
    grade = _calc_grade(score)
    passed = score >= pass_threshold and errors_total == 0

    return RunQualityReport(
        score=score,
        grade=grade,
        pass_threshold=pass_threshold,
        passed=passed,
        events_total=summary.events_total,
        invalid_json_lines=summary.invalid_json_lines,
        errors_total=errors_total,
        warnings_total=warnings_total,
        duplicate_event_ids=duplicate_event_ids,
        out_of_order_events=out_of_order_events,
        missing_trace_ids=missing_trace_ids,
        missing_order_ref_execution=missing_order_ref_execution,
        audit_gaps=len(gaps),
        penalty_breakdown=penalties,
        trades_attempted=summary.trades_attempted,
        trades_filled=summary.trades_filled,
        blocks_total=summary.blocks_total,
        no_action_by_reason=summary.no_action_by_reason,
        trade_action_by_decision=summary.trade_action_by_decision,
        risk_guard_by_decision=summary.risk_guard_by_decision,
        risk_guard_blocks_by_guard=summary.risk_guard_blocks_by_guard,
        by_event_type=summary.by_event_type,
        by_severity=summary.by_severity,
        by_source_system=summary.by_source_system,
        by_source_component=summary.by_source_component,
        by_environment=summary.by_environment,
        non_contract_event_types=summary.non_contract_event_types,
        count_unique_run_ids=summary.count_unique_run_ids,
        count_unique_session_ids=summary.count_unique_session_ids,
        count_unique_trace_ids=summary.count_unique_trace_ids,
    )

