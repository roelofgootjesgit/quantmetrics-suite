"""Daily summary services for QuantLog."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from quantlog.events.io import discover_jsonl_files, iter_jsonl_file
from quantlog.events.schema import EVENT_PAYLOAD_REQUIRED


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
    # P2 throughput: trade_action decision mix + NO_ACTION reason histogram
    trade_action_by_decision: dict[str, int]
    no_action_by_reason: dict[str, int]
    # P3: guard outcomes (BLOCK counts by guard_name for funnel analysis)
    risk_guard_by_decision: dict[str, int]
    risk_guard_blocks_by_guard: dict[str, int]
    # Pipeline: filter stage histogram (canonical reasons, same set as NO_ACTION)
    signal_filtered_by_reason: dict[str, int]
    by_severity: dict[str, int]
    by_source_system: dict[str, int]
    by_source_component: dict[str, int]
    by_environment: dict[str, int]
    # event_type strings not in EVENT_PAYLOAD_REQUIRED (typos / pre-schema / drift)
    non_contract_event_types: dict[str, int]
    # How many distinct correlation ids appear (merged folders / multi-run days)
    count_unique_run_ids: int
    count_unique_session_ids: int
    count_unique_trace_ids: int


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
    trade_action_by_decision: Counter[str] = Counter()
    no_action_by_reason: Counter[str] = Counter()
    risk_guard_by_decision: Counter[str] = Counter()
    risk_guard_blocks_by_guard: Counter[str] = Counter()
    signal_filtered_by_reason: Counter[str] = Counter()
    by_severity: Counter[str] = Counter()
    by_source_system: Counter[str] = Counter()
    by_source_component: Counter[str] = Counter()
    by_environment: Counter[str] = Counter()
    non_contract_event_types: Counter[str] = Counter()
    known_event_types = EVENT_PAYLOAD_REQUIRED.keys()
    unique_run_ids: set[str] = set()
    unique_session_ids: set[str] = set()
    unique_trace_ids: set[str] = set()

    for jsonl_path in files:
        for raw_line in iter_jsonl_file(jsonl_path):
            if raw_line.parsed is None:
                invalid_json_lines += 1
                continue
            event = raw_line.parsed
            events_total += 1
            event_type = str(event.get("event_type", "unknown"))
            by_event[event_type] += 1

            raw_et = event.get("event_type")
            if isinstance(raw_et, str) and raw_et.strip():
                et_norm = raw_et.strip()
                if et_norm not in known_event_types:
                    non_contract_event_types[et_norm] += 1

            sev = event.get("severity")
            if isinstance(sev, str) and sev.strip():
                by_severity[sev.strip()] += 1
            else:
                by_severity["<missing_or_invalid>"] += 1

            src = event.get("source_system")
            if isinstance(src, str) and src.strip():
                by_source_system[src.strip()] += 1
            else:
                by_source_system["<missing_or_invalid>"] += 1

            comp = event.get("source_component")
            if isinstance(comp, str) and comp.strip():
                by_source_component[comp.strip()] += 1
            else:
                by_source_component["<missing_or_invalid>"] += 1

            env = event.get("environment")
            if isinstance(env, str) and env.strip():
                by_environment[env.strip()] += 1
            else:
                by_environment["<missing_or_invalid>"] += 1

            rid = event.get("run_id")
            if isinstance(rid, str) and rid.strip():
                unique_run_ids.add(rid.strip())
            sid = event.get("session_id")
            if isinstance(sid, str) and sid.strip():
                unique_session_ids.add(sid.strip())
            tid = event.get("trace_id")
            if isinstance(tid, str) and tid.strip():
                unique_trace_ids.add(tid.strip())

            payload = event.get("payload")
            if not isinstance(payload, dict):
                payload = {}

            if event_type == "trade_action":
                decision = str(payload.get("decision", "")).upper()
                if decision:
                    trade_action_by_decision[decision] += 1
                if decision == "NO_ACTION":
                    raw_reason = payload.get("reason")
                    if isinstance(raw_reason, str) and raw_reason.strip():
                        no_action_by_reason[raw_reason.strip()] += 1
                    else:
                        no_action_by_reason["<missing_or_empty_reason>"] += 1
                if decision in {"ENTER", "REVERSE"}:
                    trades_attempted += 1
            elif event_type == "risk_guard_decision":
                decision = str(payload.get("decision", "")).upper()
                if decision:
                    risk_guard_by_decision[decision] += 1
                if decision == "BLOCK":
                    blocks_total += 1
                    gn = payload.get("guard_name")
                    if isinstance(gn, str) and gn.strip():
                        risk_guard_blocks_by_guard[gn.strip()] += 1
                    else:
                        risk_guard_blocks_by_guard["<missing_guard_name>"] += 1
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
            elif event_type == "signal_filtered":
                sfr = payload.get("filter_reason")
                if isinstance(sfr, str) and sfr.strip():
                    signal_filtered_by_reason[sfr.strip()] += 1
                else:
                    signal_filtered_by_reason["<missing_or_empty_filter_reason>"] += 1

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
        trade_action_by_decision=dict(trade_action_by_decision),
        no_action_by_reason=dict(no_action_by_reason),
        risk_guard_by_decision=dict(risk_guard_by_decision),
        risk_guard_blocks_by_guard=dict(risk_guard_blocks_by_guard),
        signal_filtered_by_reason=dict(signal_filtered_by_reason),
        by_severity=dict(by_severity),
        by_source_system=dict(by_source_system),
        by_source_component=dict(by_source_component),
        by_environment=dict(by_environment),
        non_contract_event_types=dict(non_contract_event_types),
        count_unique_run_ids=len(unique_run_ids),
        count_unique_session_ids=len(unique_session_ids),
        count_unique_trace_ids=len(unique_trace_ids),
    )

