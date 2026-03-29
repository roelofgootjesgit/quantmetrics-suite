"""Ingest health checks, including audit-gap detection."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from quantlog.events.io import discover_jsonl_files, iter_jsonl_file
from quantlog.ingest.emitter import EventEmitter, utc_now_iso


@dataclass(slots=True, frozen=True)
class AuditGap:
    source_system: str
    previous_ingested_at_utc: str
    current_ingested_at_utc: str
    gap_seconds: float


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def detect_audit_gaps(path: Path, max_gap_seconds: float) -> list[AuditGap]:
    rows_by_source: dict[str, list[dict[str, Any]]] = {}
    for jsonl_path in discover_jsonl_files(path):
        for raw_line in iter_jsonl_file(jsonl_path):
            if raw_line.parsed is None:
                continue
            event = raw_line.parsed
            source = str(event.get("source_system", "unknown"))
            rows_by_source.setdefault(source, []).append(event)

    gaps: list[AuditGap] = []
    for source, rows in rows_by_source.items():
        rows.sort(
            key=lambda row: _parse_dt(row.get("ingested_at_utc")) or datetime.min
        )
        previous_dt: datetime | None = None
        previous_label = ""
        for row in rows:
            current_label = str(row.get("ingested_at_utc", ""))
            current_dt = _parse_dt(current_label)
            if current_dt is None:
                continue
            if previous_dt is not None:
                delta = (current_dt - previous_dt).total_seconds()
                if delta > max_gap_seconds:
                    gaps.append(
                        AuditGap(
                            source_system=source,
                            previous_ingested_at_utc=previous_label,
                            current_ingested_at_utc=current_label,
                            gap_seconds=delta,
                        )
                    )
            previous_dt = current_dt
            previous_label = current_label
    return gaps


def emit_audit_gap_events(
    *,
    base_path: Path,
    gaps: list[AuditGap],
    trace_id: str = "trace_audit_gap_scan",
    environment: str = "shadow",
    run_id: str = "run_audit_health",
    session_id: str = "session_audit_health",
) -> list[dict[str, Any]]:
    emitter = EventEmitter(
        base_path=base_path,
        source_system="quantlog",
        source_component="ingest_health",
        environment=environment,
        run_id=run_id,
        session_id=session_id,
    )
    emitted: list[dict[str, Any]] = []
    for gap in gaps:
        emitted_event = emitter.emit_event(
            event_type="audit_gap_detected",
            trace_id=trace_id,
            severity="warn",
            payload={
                "source_system": gap.source_system,
                "gap_start_utc": gap.previous_ingested_at_utc,
                "gap_end_utc": gap.current_ingested_at_utc,
                "gap_seconds": gap.gap_seconds,
                "detected_at_utc": utc_now_iso(),
                "reason": "ingest_time_gap_exceeded_threshold",
            },
        )
        emitted.append(emitted_event)
    return emitted

