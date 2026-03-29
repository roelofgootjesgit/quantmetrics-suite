"""Daily summary services for QuantLog."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from quantlog.events.io import discover_jsonl_files, iter_jsonl_file


@dataclass(slots=True, frozen=True)
class DailySummary:
    files_scanned: int
    events_total: int
    invalid_json_lines: int
    by_event_type: dict[str, int]
    trades_attempted: int
    trades_filled: int
    blocks_total: int
    broker_rejects: int
    failsafe_pauses: int
    audit_gaps_detected: int
    avg_slippage: float | None
    median_slippage: float | None


def _median(values: list[float]) -> float | None:
    if not values:
        return None
    sorted_values = sorted(values)
    n = len(sorted_values)
    mid = n // 2
    if n % 2 == 1:
        return sorted_values[mid]
    return (sorted_values[mid - 1] + sorted_values[mid]) / 2.0


def summarize_path(path: Path) -> DailySummary:
    files = discover_jsonl_files(path)
    by_event = Counter()
    invalid_json_lines = 0
    events_total = 0
    trades_attempted = 0
    trades_filled = 0
    blocks_total = 0
    broker_rejects = 0
    failsafe_pauses = 0
    audit_gaps_detected = 0
    slippages: list[float] = []

    for jsonl_path in files:
        for raw_line in iter_jsonl_file(jsonl_path):
            if raw_line.parsed is None:
                invalid_json_lines += 1
                continue
            event = raw_line.parsed
            events_total += 1
            event_type = str(event.get("event_type", "unknown"))
            by_event[event_type] += 1

            payload = event.get("payload")
            if not isinstance(payload, dict):
                payload = {}

            if event_type == "trade_action":
                decision = str(payload.get("decision", "")).upper()
                if decision in {"ENTER", "REVERSE"}:
                    trades_attempted += 1
            elif event_type == "risk_guard_decision":
                decision = str(payload.get("decision", "")).upper()
                if decision == "BLOCK":
                    blocks_total += 1
            elif event_type == "order_filled":
                trades_filled += 1
                slippage = payload.get("slippage")
                if isinstance(slippage, (int, float)):
                    slippages.append(float(slippage))
            elif event_type == "order_rejected":
                broker_rejects += 1
            elif event_type == "failsafe_pause":
                failsafe_pauses += 1
            elif event_type == "audit_gap_detected":
                audit_gaps_detected += 1

    avg_slippage = (sum(slippages) / len(slippages)) if slippages else None
    median_slippage = _median(slippages)

    return DailySummary(
        files_scanned=len(files),
        events_total=events_total,
        invalid_json_lines=invalid_json_lines,
        by_event_type=dict(by_event),
        trades_attempted=trades_attempted,
        trades_filled=trades_filled,
        blocks_total=blocks_total,
        broker_rejects=broker_rejects,
        failsafe_pauses=failsafe_pauses,
        audit_gaps_detected=audit_gaps_detected,
        avg_slippage=avg_slippage,
        median_slippage=median_slippage,
    )

