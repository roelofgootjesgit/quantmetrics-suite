"""QuantLog event validation."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

from quantlog.events.io import RawEventLine, discover_jsonl_files, iter_jsonl_file
from quantlog.events.schema import (
    ALLOWED_ENVIRONMENTS,
    ALLOWED_SEVERITIES,
    ALLOWED_SOURCE_SYSTEMS,
    CLOSEST_TO_ENTRY_SIDES,
    COMBO_MODULE_LABELS,
    EVENT_PAYLOAD_REQUIRED,
    GATE_SUMMARY_GATE_KEYS,
    GATE_SUMMARY_STATUSES,
    NO_ACTION_REASONS_ALLOWED,
    REQUIRED_ENVELOPE_FIELDS,
    RISK_GUARD_DECISIONS,
    TRADE_ACTION_DECISIONS,
    TRADE_EXECUTED_DIRECTIONS,
    DECISION_CHAIN_EVENT_TYPES,
    DECISION_CHAIN_EVENT_ORDER_RANK,
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


def _num_in_closed_unit_interval(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return 0.0 <= float(value) <= 1.0
    return False


def _non_negative_int_not_bool(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _signal_evaluated_optional_issues(payload: dict[str, Any]) -> list[tuple[str, str]]:
    """Return (level, message) tuples for optional `signal_evaluated` desk-grade fields."""
    rows: list[tuple[str, str]] = []

    gs = payload.get("gate_summary")
    if gs is not None:
        if not isinstance(gs, dict):
            rows.append(("error", "signal_evaluated_invalid_gate_summary_not_object"))
        else:
            for gate_key, gate_val in gs.items():
                if gate_key not in GATE_SUMMARY_GATE_KEYS:
                    rows.append(("warn", f"signal_evaluated_unknown_gate_summary_key: {gate_key!r}"))
                else:
                    if (
                        not isinstance(gate_val, str)
                        or gate_val not in GATE_SUMMARY_STATUSES
                    ):
                        rows.append(
                            (
                                "error",
                                f"signal_evaluated_invalid_gate_summary_status[{gate_key}]: {gate_val!r}",
                            )
                        )

    def _blocking_gate(field: str) -> None:
        if field not in payload:
            return
        val = payload[field]
        if val is None:
            return
        if not isinstance(val, str) or val not in GATE_SUMMARY_GATE_KEYS:
            rows.append(("error", f"signal_evaluated_invalid_{field}: {val!r}"))

    _blocking_gate("blocked_by_primary_gate")
    _blocking_gate("blocked_by_secondary_gate")

    ep = payload.get("evaluation_path")
    if ep is not None:
        if not isinstance(ep, list):
            rows.append(("error", "signal_evaluated_invalid_evaluation_path_not_array"))
        else:
            for idx, seg in enumerate(ep):
                if not isinstance(seg, str):
                    rows.append(
                        (
                            "error",
                            f"signal_evaluated_invalid_evaluation_path_segment[{idx}]: {seg!r}",
                        )
                    )
                elif seg not in GATE_SUMMARY_GATE_KEYS:
                    rows.append(
                        ("warn", f"signal_evaluated_unknown_evaluation_path_gate: {seg!r}")
                    )

    if "new_bar_detected" in payload and not isinstance(payload["new_bar_detected"], bool):
        rows.append(("error", f"signal_evaluated_invalid_new_bar_detected: {payload['new_bar_detected']!r}"))
    if "same_bar_guard_triggered" in payload and not isinstance(
        payload["same_bar_guard_triggered"], bool
    ):
        rows.append(
            (
                "error",
                f"signal_evaluated_invalid_same_bar_guard_triggered: {payload['same_bar_guard_triggered']!r}",
            )
        )

    sk = payload.get("same_bar_skip_count_for_bar")
    if sk is not None and not _non_negative_int_not_bool(sk):
        rows.append(("error", f"signal_evaluated_invalid_same_bar_skip_count_for_bar: {sk!r}"))

    for ts_key in ("bar_ts", "poll_ts"):
        if ts_key in payload and payload[ts_key] is not None:
            if not _is_utc_iso8601(payload[ts_key]):
                rows.append(("error", f"signal_evaluated_invalid_{ts_key}"))

    ns = payload.get("near_entry_score")
    if ns is not None and not _num_in_closed_unit_interval(ns):
        rows.append(("error", f"signal_evaluated_invalid_near_entry_score: {ns!r}"))

    for k in ("combo_active_modules_count_long", "combo_active_modules_count_short", "active_modules_count_long", "active_modules_count_short"):
        if k in payload and payload[k] is not None:
            v = payload[k]
            if not _non_negative_int_not_bool(v):
                rows.append(("error", f"signal_evaluated_invalid_{k}: {v!r}"))

    for k in ("entry_distance_long", "entry_distance_short"):
        if k in payload and payload[k] is not None:
            v = payload[k]
            if not _non_negative_int_not_bool(v):
                rows.append(("error", f"signal_evaluated_invalid_{k}: {v!r}"))

    ces = payload.get("closest_to_entry_side")
    if ces is not None and (not isinstance(ces, str) or ces not in CLOSEST_TO_ENTRY_SIDES):
        rows.append(("error", f"signal_evaluated_invalid_closest_to_entry_side: {ces!r}"))

    for side_key in ("missing_modules_long", "missing_modules_short"):
        arr = payload.get(side_key)
        if arr is None:
            continue
        if not isinstance(arr, list):
            rows.append(("error", f"signal_evaluated_invalid_{side_key}_not_array"))
            continue
        for item in arr:
            if not isinstance(item, str) or item not in COMBO_MODULE_LABELS:
                rows.append(("error", f"signal_evaluated_invalid_{side_key}_label: {item!r}"))

    for mod_key in ("modules_long", "modules_short"):
        mobj = payload.get(mod_key)
        if mobj is None:
            continue
        if not isinstance(mobj, dict):
            rows.append(("error", f"signal_evaluated_invalid_{mod_key}_not_object"))
            continue
        for mk, mv in mobj.items():
            if mk not in COMBO_MODULE_LABELS:
                rows.append(("warn", f"signal_evaluated_unknown_module_key[{mod_key}]: {mk!r}"))
            if not isinstance(mv, bool):
                rows.append(("error", f"signal_evaluated_invalid_{mod_key}[{mk}]: {mv!r}"))

    for bkey in ("setup_candidate", "entry_ready"):
        if bkey in payload and not isinstance(payload[bkey], bool):
            rows.append(("error", f"signal_evaluated_invalid_{bkey}: {payload[bkey]!r}"))

    cs = payload.get("candidate_strength")
    if cs is not None and not _num_in_closed_unit_interval(cs):
        rows.append(("error", f"signal_evaluated_invalid_candidate_strength: {cs!r}"))

    tsnap = payload.get("threshold_snapshot")
    if tsnap is not None and not isinstance(tsnap, dict):
        rows.append(("error", "signal_evaluated_invalid_threshold_snapshot_not_object"))

    return rows


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

    ss = event.get("source_system")
    et_chain = event.get("event_type")
    if ss == "quantbuild" and et_chain in DECISION_CHAIN_EVENT_TYPES:
        dcid = event.get("decision_cycle_id")
        if not isinstance(dcid, str) or not dcid.strip():
            issues.append(
                ValidationIssue(
                    level="error",
                    path=raw_line.path,
                    line_number=raw_line.line_number,
                    message="missing_decision_cycle_id_quantbuild_chain",
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

    if isinstance(payload, dict):
        for key in ("trade_id", "order_ref"):
            ev_v = event.get(key)
            pl_v = payload.get(key)
            if (
                isinstance(ev_v, str)
                and ev_v.strip()
                and isinstance(pl_v, str)
                and pl_v.strip()
                and ev_v.strip() != pl_v.strip()
            ):
                issues.append(
                    ValidationIssue(
                        level="error",
                        path=raw_line.path,
                        line_number=raw_line.line_number,
                        message=f"{key}_envelope_payload_mismatch",
                    )
                )

    if event_type == "signal_evaluated" and isinstance(payload, dict):
        for level, msg in _signal_evaluated_optional_issues(payload):
            issues.append(
                ValidationIssue(
                    level=level,
                    path=raw_line.path,
                    line_number=raw_line.line_number,
                    message=msg,
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
        elif decision == "ENTER":
            tid = payload.get("trade_id")
            if not isinstance(tid, str) or not tid.strip():
                issues.append(
                    ValidationIssue(
                        level="error",
                        path=raw_line.path,
                        line_number=raw_line.line_number,
                        message="trade_action_enter_missing_trade_id",
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

    if event_type == "signal_filtered" and isinstance(payload, dict):
        fr = payload.get("filter_reason")
        if not isinstance(fr, str) or fr not in NO_ACTION_REASONS_ALLOWED:
            issues.append(
                ValidationIssue(
                    level="error",
                    path=raw_line.path,
                    line_number=raw_line.line_number,
                    message=f"invalid_signal_filtered_reason: {fr!r}",
                )
            )

    if event_type == "trade_executed" and isinstance(payload, dict):
        direction = str(payload.get("direction", "")).upper()
        if direction not in TRADE_EXECUTED_DIRECTIONS:
            issues.append(
                ValidationIssue(
                    level="error",
                    path=raw_line.path,
                    line_number=raw_line.line_number,
                    message=f"invalid_trade_executed_direction: {direction}",
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

    if event_type == "trade_executed" and not event.get("order_ref"):
        issues.append(
            ValidationIssue(
                level="warn",
                path=raw_line.path,
                line_number=raw_line.line_number,
                message="trade_executed_missing_order_ref",
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


def _canonical_trade_id(event: dict[str, Any]) -> str | None:
    """Prefer envelope ``trade_id``, then payload (for correlating mixed producers)."""
    te = event.get("trade_id")
    if isinstance(te, str) and te.strip():
        return te.strip()
    pl = event.get("payload")
    if isinstance(pl, dict):
        pt = pl.get("trade_id")
        if isinstance(pt, str) and pt.strip():
            return pt.strip()
    return None


def _canonical_order_ref(event: dict[str, Any]) -> str | None:
    eo = event.get("order_ref")
    if isinstance(eo, str) and eo.strip():
        return eo.strip()
    pl = event.get("payload")
    if isinstance(pl, dict):
        po = pl.get("order_ref")
        if isinstance(po, str) and po.strip():
            return po.strip()
    return None


def _canonical_symbol(event: dict[str, Any]) -> str | None:
    sym = event.get("symbol")
    if isinstance(sym, str) and sym.strip():
        return sym.strip()
    return None


def _referential_correlation_issues(rows: list[tuple[Path, int, dict[str, Any]]]) -> list[ValidationIssue]:
    """Stable ``trade_id`` / ``order_ref`` correlation across schema-valid rows (see canonical doc §2.2)."""
    issues: list[ValidationIssue] = []
    trade_seen: dict[str, tuple[str, str, str, str | None]] = {}
    order_seen: dict[str, tuple[str, str, str | None]] = {}

    for path, line_no, ev in rows:
        rid = ev.get("run_id")
        sid = ev.get("session_id")
        tr = ev.get("trace_id")
        if not (
            isinstance(rid, str)
            and rid.strip()
            and isinstance(sid, str)
            and sid.strip()
            and isinstance(tr, str)
            and tr.strip()
        ):
            continue
        rs, ss, ts = rid.strip(), sid.strip(), tr.strip()

        sym = _canonical_symbol(ev)
        ctid = _canonical_trade_id(ev)

        if ctid:
            prev = trade_seen.get(ctid)
            if prev is None:
                trade_seen[ctid] = (rs, ss, ts, sym)
            else:
                pr, ps, pt, psym = prev
                if (rs, ss, ts) != (pr, ps, pt):
                    issues.append(
                        ValidationIssue(
                            level="error",
                            path=path,
                            line_number=line_no,
                            message=(
                                "trade_id_correlation_mismatch: "
                                f"trade_id={ctid!r} "
                                f"expected_run_session_trace=({pr!r},{ps!r},{pt!r}) "
                                f"got=({rs!r},{ss!r},{ts!r})"
                            ),
                        )
                    )
                elif psym is not None and sym is not None and psym != sym:
                    issues.append(
                        ValidationIssue(
                            level="error",
                            path=path,
                            line_number=line_no,
                            message=(
                                "trade_id_symbol_mismatch: "
                                f"trade_id={ctid!r} "
                                f"expected_symbol={psym!r} got_symbol={sym!r}"
                            ),
                        )
                    )
                else:
                    merged = psym or sym
                    trade_seen[ctid] = (pr, ps, pt, merged)

        cor = _canonical_order_ref(ev)
        if cor:
            prev_o = order_seen.get(cor)
            if prev_o is None:
                order_seen[cor] = (rs, ss, ctid)
            else:
                pr, ps, ptid = prev_o
                if (rs, ss) != (pr, ps):
                    issues.append(
                        ValidationIssue(
                            level="error",
                            path=path,
                            line_number=line_no,
                            message=(
                                "order_ref_run_session_mismatch: "
                                f"order_ref={cor!r} "
                                f"expected_run_session=({pr!r},{ps!r}) "
                                f"got=({rs!r},{ss!r})"
                            ),
                        )
                    )
                elif ptid is not None and ctid is not None and ptid != ctid:
                    issues.append(
                        ValidationIssue(
                            level="error",
                            path=path,
                            line_number=line_no,
                            message=(
                                "order_ref_trade_id_mismatch: "
                                f"order_ref={cor!r} "
                                f"expected_trade_id={ptid!r} got_trade_id={ctid!r}"
                            ),
                        )
                    )
                elif ptid is None and ctid is not None:
                    order_seen[cor] = (pr, ps, ctid)

    return issues


def _decision_cycle_trade_linkage_issues(
    rows: list[tuple[Path, int, dict[str, Any]]],
) -> list[ValidationIssue]:
    """ENTER maps ``decision_cycle_id`` → ``trade_id``; later rows with both must match (§2.3)."""
    issues: list[ValidationIssue] = []
    dc_to_tid: dict[str, str] = {}

    for path, line_no, ev in rows:
        if ev.get("source_system") != "quantbuild" or ev.get("event_type") != "trade_action":
            continue
        pl = ev.get("payload")
        if not isinstance(pl, dict):
            continue
        if str(pl.get("decision", "")).strip().upper() != "ENTER":
            continue
        dc = ev.get("decision_cycle_id")
        if not isinstance(dc, str) or not dc.strip():
            continue
        dc_s = dc.strip()
        tid = _canonical_trade_id(ev)
        if tid is None:
            continue
        prev = dc_to_tid.get(dc_s)
        if prev is not None and prev != tid:
            issues.append(
                ValidationIssue(
                    level="error",
                    path=path,
                    line_number=line_no,
                    message=(
                        "decision_cycle_enter_trade_id_conflict: "
                        f"decision_cycle_id={dc_s!r} "
                        f"first_trade_id={prev!r} conflicting_trade_id={tid!r}"
                    ),
                )
            )
        else:
            dc_to_tid.setdefault(dc_s, tid)

    for path, line_no, ev in rows:
        dc = ev.get("decision_cycle_id")
        if not isinstance(dc, str) or not dc.strip():
            continue
        dc_s = dc.strip()
        if dc_s not in dc_to_tid:
            continue
        exp = dc_to_tid[dc_s]
        tid = _canonical_trade_id(ev)
        if tid is None:
            continue
        if tid != exp:
            issues.append(
                ValidationIssue(
                    level="error",
                    path=path,
                    line_number=line_no,
                    message=(
                        "decision_cycle_trade_id_linkage_mismatch: "
                        f"decision_cycle_id={dc_s!r} "
                        f"expected_trade_id_from_enter={exp!r} got_trade_id={tid!r}"
                    ),
                )
            )

    return issues


@dataclass(slots=True, frozen=True)
class _DecisionChainAnchor:
    path: Path
    line_number: int
    decision_cycle_id: str
    event_type: str
    sort_key: tuple[Any, ...]
    run_id: str
    session_id: str
    trace_id: str
    symbol: str | None


_FALLBACK_SORT_END = datetime(9999, 12, 31, 23, 59, 59, tzinfo=timezone.utc)


def _timestamp_sort_key(timestamp_utc: Any, path: Path, line_number: int) -> tuple[Any, ...]:
    if isinstance(timestamp_utc, str):
        try:
            dt = datetime.fromisoformat(timestamp_utc.replace("Z", "+00:00"))
            return (dt, str(path), line_number)
        except ValueError:
            pass
    return (_FALLBACK_SORT_END, str(path), line_number)


def _decision_cycle_sequence_issues(anchors: list[_DecisionChainAnchor]) -> list[ValidationIssue]:
    """Cross-event checks per ``decision_cycle_id`` (QuantBuild chain only)."""
    issues: list[ValidationIssue] = []
    by_cycle: dict[str, list[_DecisionChainAnchor]] = {}
    for a in anchors:
        by_cycle.setdefault(a.decision_cycle_id, []).append(a)

    for dc_id, group in by_cycle.items():
        sorted_group = sorted(group, key=lambda x: x.sort_key)

        ref = sorted_group[0]
        ref_run, ref_sess, ref_trace = ref.run_id, ref.session_id, ref.trace_id
        symbols_nonempty = [a.symbol for a in sorted_group if a.symbol]
        ref_symbol = symbols_nonempty[0] if symbols_nonempty else None

        for a in sorted_group:
            if a.run_id != ref_run:
                issues.append(
                    ValidationIssue(
                        level="error",
                        path=a.path,
                        line_number=a.line_number,
                        message=(
                            "decision_cycle_run_id_mismatch: "
                            f"decision_cycle_id={dc_id!r} "
                            f"expected_run_id={ref_run!r} got_run_id={a.run_id!r}"
                        ),
                    )
                )
            if a.session_id != ref_sess:
                issues.append(
                    ValidationIssue(
                        level="error",
                        path=a.path,
                        line_number=a.line_number,
                        message=(
                            "decision_cycle_session_id_mismatch: "
                            f"decision_cycle_id={dc_id!r} "
                            f"expected_session_id={ref_sess!r} got_session_id={a.session_id!r}"
                        ),
                    )
                )
            if a.trace_id != ref_trace:
                issues.append(
                    ValidationIssue(
                        level="error",
                        path=a.path,
                        line_number=a.line_number,
                        message=(
                            "decision_cycle_trace_id_mismatch: "
                            f"decision_cycle_id={dc_id!r} "
                            f"expected_trace_id={ref_trace!r} got_trace_id={a.trace_id!r}"
                        ),
                    )
                )
            if ref_symbol is not None and a.symbol is not None and a.symbol != ref_symbol:
                issues.append(
                    ValidationIssue(
                        level="error",
                        path=a.path,
                        line_number=a.line_number,
                        message=(
                            "decision_cycle_symbol_mismatch: "
                            f"decision_cycle_id={dc_id!r} "
                            f"expected_symbol={ref_symbol!r} got_symbol={a.symbol!r}"
                        ),
                    )
                )
            elif ref_symbol is not None and a.symbol is None:
                issues.append(
                    ValidationIssue(
                        level="warn",
                        path=a.path,
                        line_number=a.line_number,
                        message=(
                            "decision_cycle_symbol_omitted: "
                            f"decision_cycle_id={dc_id!r} "
                            f"expected_symbol={ref_symbol!r}"
                        ),
                    )
                )

        trade_lines = [x for x in sorted_group if x.event_type == "trade_action"]

        if not trade_lines:
            last = sorted_group[-1]
            issues.append(
                ValidationIssue(
                    level="error",
                    path=last.path,
                    line_number=last.line_number,
                    message=f"decision_cycle_missing_trade_action: decision_cycle_id={dc_id!r}",
                )
            )
        elif len(trade_lines) > 1:
            for dup in trade_lines:
                issues.append(
                    ValidationIssue(
                        level="error",
                        path=dup.path,
                        line_number=dup.line_number,
                        message=(
                            "duplicate_trade_action_decision_cycle: "
                            f"decision_cycle_id={dc_id!r}"
                        ),
                    )
                )

        prev_rank = -1
        prev_type: str | None = None
        for a in sorted_group:
            rank = DECISION_CHAIN_EVENT_ORDER_RANK.get(a.event_type)
            if rank is None:
                continue
            if rank < prev_rank:
                issues.append(
                    ValidationIssue(
                        level="error",
                        path=a.path,
                        line_number=a.line_number,
                        message=(
                            "decision_chain_order_violation: "
                            f"decision_cycle_id={dc_id!r} "
                            f"after_event_type={prev_type!r} "
                            f"event_type={a.event_type!r}"
                        ),
                    )
                )
            prev_rank = max(prev_rank, rank)
            prev_type = a.event_type

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
    schema_ok_lines: set[tuple[Path, int]] = set()
    chain_anchors: list[_DecisionChainAnchor] = []
    ref_rows: list[tuple[Path, int, dict[str, Any]]] = []

    for jsonl_path in jsonl_files:
        seq_last: dict[str, int] = {}
        for raw_line in iter_jsonl_file(jsonl_path):
            lines_scanned += 1
            event_issues = validate_raw_event(raw_line)
            mono_issues = _monotonic_source_seq_issues(raw_line, seq_last)
            combined = event_issues + mono_issues
            issues.extend(combined)
            line_ok = not any(issue.level == "error" for issue in combined)
            if line_ok:
                schema_ok_lines.add((raw_line.path, raw_line.line_number))

            ev = raw_line.parsed
            if isinstance(ev, dict) and line_ok:
                ref_rows.append((raw_line.path, raw_line.line_number, ev))
                dc = ev.get("decision_cycle_id")
                et = ev.get("event_type")
                ts = ev.get("timestamp_utc")
                if (
                    ev.get("source_system") == "quantbuild"
                    and isinstance(et, str)
                    and et in DECISION_CHAIN_EVENT_TYPES
                    and isinstance(dc, str)
                    and dc.strip()
                ):
                    rid = ev.get("run_id")
                    sess = ev.get("session_id")
                    trid = ev.get("trace_id")
                    if (
                        isinstance(rid, str)
                        and rid.strip()
                        and isinstance(sess, str)
                        and sess.strip()
                        and isinstance(trid, str)
                        and trid.strip()
                    ):
                        chain_anchors.append(
                            _DecisionChainAnchor(
                                path=raw_line.path,
                                line_number=raw_line.line_number,
                                decision_cycle_id=dc.strip(),
                                event_type=et,
                                sort_key=_timestamp_sort_key(
                                    ts, raw_line.path, raw_line.line_number
                                ),
                                run_id=rid.strip(),
                                session_id=sess.strip(),
                                trace_id=trid.strip(),
                                symbol=_canonical_symbol(ev),
                            )
                        )

    seq_issues = _decision_cycle_sequence_issues(chain_anchors)
    issues.extend(seq_issues)
    for si in seq_issues:
        if si.level == "error":
            schema_ok_lines.discard((si.path, si.line_number))

    ref_issues = _referential_correlation_issues(ref_rows)
    issues.extend(ref_issues)
    for ri in ref_issues:
        if ri.level == "error":
            schema_ok_lines.discard((ri.path, ri.line_number))

    link_issues = _decision_cycle_trade_linkage_issues(ref_rows)
    issues.extend(link_issues)
    for li in link_issues:
        if li.level == "error":
            schema_ok_lines.discard((li.path, li.line_number))

    return ValidationReport(
        files_scanned=len(jsonl_files),
        lines_scanned=lines_scanned,
        events_valid=len(schema_ok_lines),
        issues=issues,
    )

