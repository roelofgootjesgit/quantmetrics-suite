"""Canonical QuantLog v1 event schema constants."""

from __future__ import annotations

from typing import Final

REQUIRED_ENVELOPE_FIELDS: Final[set[str]] = {
    "event_id",
    "event_type",
    "event_version",
    "timestamp_utc",
    "ingested_at_utc",
    "source_system",
    "source_component",
    "environment",
    "run_id",
    "session_id",
    "source_seq",
    "trace_id",
    "severity",
    "payload",
}

ALLOWED_SOURCE_SYSTEMS: Final[set[str]] = {"quantbuild", "quantbridge", "quantlog"}
ALLOWED_SEVERITIES: Final[set[str]] = {"info", "warn", "error", "critical"}
ALLOWED_ENVIRONMENTS: Final[set[str]] = {"paper", "dry_run", "live", "shadow"}

EVENT_PAYLOAD_REQUIRED: Final[dict[str, set[str]]] = {
    "signal_evaluated": {"signal_type", "signal_direction", "confidence"},
    "risk_guard_decision": {"guard_name", "decision", "reason"},
    "trade_action": {"decision", "reason"},
    "adaptive_mode_transition": {"old_mode", "new_mode", "reason"},
    "broker_connect": {"broker", "status"},
    "order_submitted": {"order_ref", "side", "volume"},
    "order_filled": {"order_ref", "fill_price"},
    "order_rejected": {"order_ref", "reason"},
    "governance_state_changed": {"account_id", "old_state", "new_state", "reason"},
    "failsafe_pause": {"reason"},
    "audit_gap_detected": {
        "source_system",
        "gap_start_utc",
        "gap_end_utc",
        "gap_seconds",
        "reason",
    },
}

TRADE_ACTION_DECISIONS: Final[set[str]] = {"ENTER", "EXIT", "REVERSE", "NO_ACTION"}
RISK_GUARD_DECISIONS: Final[set[str]] = {"ALLOW", "BLOCK", "REDUCE", "DELAY"}

