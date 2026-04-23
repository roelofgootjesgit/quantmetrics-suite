"""Canonical QuantLog v1 event schema constants."""

from __future__ import annotations

from typing import Final

# QuantBuild decision chain: these require a non-empty ``decision_cycle_id`` on the envelope
# (see quantmetrics_os / QUANT_STACK_CANONICAL_IDS_AND_GRAINS).
DECISION_CHAIN_EVENT_TYPES: Final[frozenset[str]] = frozenset(
    {
        "signal_detected",
        "signal_evaluated",
        "risk_guard_decision",
        "trade_action",
    }
)

# Monotonic order within a single decision_cycle_id (see QUANT_STACK_CANONICAL_IDS_AND_GRAINS).
DECISION_CHAIN_EVENT_ORDER_RANK: Final[dict[str, int]] = {
    "signal_detected": 0,
    "signal_evaluated": 1,
    "risk_guard_decision": 2,
    "trade_action": 3,
}

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

ALLOWED_SOURCE_SYSTEMS: Final[set[str]] = {"quantbuild", "quantbridge", "quantlog", "execution"}
ALLOWED_SEVERITIES: Final[set[str]] = {"info", "warn", "error", "critical"}
ALLOWED_ENVIRONMENTS: Final[set[str]] = {"paper", "dry_run", "live", "shadow"}

EVENT_PAYLOAD_REQUIRED: Final[dict[str, set[str]]] = {
    "signal_evaluated": {"signal_type", "signal_direction", "confidence"},
    # QuantBuild pipeline: raw ICT/SQE hit before filters (see QuantBuild LiveRunner).
    "signal_detected": {
        "signal_id",
        "type",
        "direction",
        "strength",
        "bar_timestamp",
        "session",
        "regime",
    },
    # Filter stage: canonical filter_reason matches trade_action NO_ACTION reason set.
    "signal_filtered": {"filter_reason", "raw_reason"},
    "risk_guard_decision": {"guard_name", "decision", "reason"},
    "trade_action": {"decision", "reason"},
    # Confirmed registration after ENTER (QuantBuild; envelope should carry order_ref when known).
    "trade_executed": {"direction", "trade_id"},
    "trade_closed": {"trade_id", "exit_price", "pnl_r"},
    "adaptive_mode_transition": {"old_mode", "new_mode", "reason"},
    "broker_connect": {"broker", "status"},
    "order_submitted": {"order_ref", "side", "volume", "trade_id"},
    "order_filled": {"order_ref", "fill_price", "trade_id"},
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
    # QuantBuild live: 15m bar index lags wall clock during entry session (data freshness).
    "market_data_stale_warning": {
        "symbol",
        "bar_lag_minutes",
        "latest_bar_ts_utc",
        "session",
        "threshold_minutes",
    },
}

TRADE_ACTION_DECISIONS: Final[set[str]] = {"ENTER", "EXIT", "REVERSE", "NO_ACTION"}
RISK_GUARD_DECISIONS: Final[set[str]] = {"ALLOW", "BLOCK", "REDUCE", "DELAY"}
TRADE_EXECUTED_DIRECTIONS: Final[set[str]] = {"LONG", "SHORT"}

# Observability: every non-trade must state why. `trade_action` with decision=NO_ACTION
# must use exactly one of these snake_case reason values (validated in validator.py).
NO_ACTION_REASONS_CORE: Final[set[str]] = {
    "no_setup",
    "regime_blocked",
    "session_blocked",
    "risk_blocked",
    "spread_too_high",
    "news_filter_active",
}
NO_ACTION_REASONS_EXTENDED: Final[set[str]] = {
    "position_limit_reached",
    "cooldown_active",
    "broker_unavailable",
    "market_data_unavailable",
    "execution_disabled",
    "confidence_too_low",
}
NO_ACTION_REASONS_ALLOWED: Final[set[str]] = NO_ACTION_REASONS_CORE | NO_ACTION_REASONS_EXTENDED

# --- signal_evaluated optional “desk-grade” upgrade (validated when emitters populate) ---

GATE_SUMMARY_GATE_KEYS: Final[frozenset[str]] = frozenset(
    {
        "session_gate",
        "regime_gate",
        "structure_gate",
        "liquidity_gate",
        "trigger_gate",
        "same_bar_guard",
        "risk_gate",
    }
)

GATE_SUMMARY_STATUSES: Final[frozenset[str]] = frozenset({"pass", "fail", "not_reached"})

COMBO_MODULE_LABELS: Final[frozenset[str]] = frozenset({"structure", "liquidity", "trigger"})

CLOSEST_TO_ENTRY_SIDES: Final[frozenset[str]] = frozenset({"long", "short", "none"})

SIGNAL_EVALUATED_OPTIONAL_PAYLOAD_KEYS: Final[tuple[str, ...]] = tuple(
    sorted(
        {
            "active_modules_count_long",
            "active_modules_count_short",
            "bar_ts",
            "blocked_by_primary_gate",
            "blocked_by_secondary_gate",
            "candidate_reason",
            "candidate_side",
            "candidate_strength",
            "closest_to_entry_side",
            "combo_active_modules_count_long",
            "combo_active_modules_count_short",
            "entry_distance_long",
            "entry_distance_short",
            "entry_ready",
            "evaluation_path",
            "gate_summary",
            "missing_modules_long",
            "missing_modules_short",
            "modules_long",
            "modules_short",
            "near_entry_score",
            "new_bar_detected",
            "poll_ts",
            "previous_eval_stage_on_bar",
            "same_bar_guard_reason",
            "same_bar_guard_triggered",
            "same_bar_skip_count_for_bar",
            "setup_candidate",
            "threshold_snapshot",
        }
    )
)

