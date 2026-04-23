"""Replay services for QuantLog."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from quantlog.events.io import discover_jsonl_files, iter_jsonl_file


@dataclass(slots=True, frozen=True)
class ReplayItem:
    timestamp_utc: str
    source_seq: int
    source_system: str
    event_type: str
    trace_id: str
    summary: str
    payload: dict[str, Any]


def _safe_dt(value: str | None) -> datetime:
    if not value:
        return datetime.min
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return datetime.min


def _summary_for_event(event: dict[str, Any]) -> str:
    event_type = event.get("event_type", "unknown")
    payload = event.get("payload", {}) if isinstance(event.get("payload"), dict) else {}

    if event_type == "risk_guard_decision":
        return f"{payload.get('guard_name', 'guard')} -> {payload.get('decision', '?')}"
    if event_type == "trade_action":
        return f"{payload.get('decision', '?')} ({payload.get('reason', 'no_reason')})"
    if event_type == "signal_detected":
        return f"{payload.get('direction', '?')} {payload.get('type', '?')} @ {payload.get('bar_timestamp', '?')}"
    if event_type == "signal_filtered":
        return f"{payload.get('filter_reason', '?')} (raw={payload.get('raw_reason', '?')})"
    if event_type == "trade_executed":
        return f"{payload.get('direction', '?')} trade_id={payload.get('trade_id', '?')}"
    if event_type in {"order_submitted", "order_filled", "order_rejected"}:
        return f"order_ref={payload.get('order_ref', event.get('order_ref', 'n/a'))}"
    if event_type == "governance_state_changed":
        return f"{payload.get('old_state', '?')} -> {payload.get('new_state', '?')}"
    if event_type == "market_data_stale_warning":
        return (
            f"lag={payload.get('bar_lag_minutes', '?')}m "
            f"latest={payload.get('latest_bar_ts_utc', '?')} "
            f"thr={payload.get('threshold_minutes', '?')}m"
        )
    return event_type


def replay_trace(path: Path, trace_id: str) -> list[ReplayItem]:
    rows: list[dict[str, Any]] = []
    for jsonl_path in discover_jsonl_files(path):
        for raw_line in iter_jsonl_file(jsonl_path):
            if raw_line.parsed is None:
                continue
            event = raw_line.parsed
            if event.get("trace_id") == trace_id:
                rows.append(event)

    rows.sort(
        key=lambda item: (
            _safe_dt(item.get("timestamp_utc")),
            int(item.get("source_seq", 0)),
            _safe_dt(item.get("ingested_at_utc")),
        )
    )

    result: list[ReplayItem] = []
    for event in rows:
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        result.append(
            ReplayItem(
                timestamp_utc=str(event.get("timestamp_utc", "")),
                source_seq=int(event.get("source_seq", 0)),
                source_system=str(event.get("source_system", "")),
                event_type=str(event.get("event_type", "")),
                trace_id=str(event.get("trace_id", "")),
                summary=_summary_for_event(event),
                payload=payload,
            )
        )
    return result

