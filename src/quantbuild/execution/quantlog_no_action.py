"""Map internal decision strings to QuantLog canonical trade_action.reason for NO_ACTION.

See QuantLog: NO_ACTION_REASONS_ALLOWED (configs/schema_registry.yaml).
"""

from __future__ import annotations

# Subset documented for operators — full set lives in QuantLog validator.
# Keep in sync with QuantLog `NO_ACTION_REASONS_ALLOWED` (schema + validator).
_CANONICAL_NO_ACTION: frozenset[str] = frozenset(
    {
        "no_setup",
        "regime_blocked",
        "session_blocked",
        "risk_blocked",
        "spread_too_high",
        "news_filter_active",
        "position_limit_reached",
        "cooldown_active",
        "broker_unavailable",
        "market_data_unavailable",
        "execution_disabled",
        "confidence_too_low",
    }
)

# Every internal code emitted as trade_action NO_ACTION from live_runner must appear here.
_INTERNAL_TO_CANONICAL: dict[str, str] = {
    # _check_signals early exits (internal log reason -> canonical)
    "regime_block": "regime_blocked",
    "outside_killzone": "session_blocked",
    "time_filter_block": "session_blocked",
    "position_limit_block": "position_limit_reached",
    "daily_loss_block": "risk_blocked",
    "bars_missing": "market_data_unavailable",
    "same_bar_already_processed": "cooldown_active",
    "no_entry_signal": "no_setup",
    # _evaluate_and_execute
    "news_block": "news_filter_active",
    "llm_advice_block": "confidence_too_low",
    "spread_block": "spread_too_high",
    "atr_unavailable": "market_data_unavailable",
    "risk_block": "risk_blocked",
    "execution_exception": "broker_unavailable",
    "execution_reject": "broker_unavailable",
    "slippage_block": "risk_blocked",
    "price_unavailable": "broker_unavailable",
}

LIVE_RUNNER_NO_ACTION_INTERNAL_CODES: frozenset[str] = frozenset(_INTERNAL_TO_CANONICAL.keys())


def canonical_no_action_reason(reason: str) -> str:
    """Return QuantLog-valid NO_ACTION reason.

    Accepts either an internal code (e.g. ``news_block``) or an already-canonical value.
    Unknown strings default to ``risk_blocked``.
    """
    if reason in _CANONICAL_NO_ACTION:
        return reason
    return _INTERNAL_TO_CANONICAL.get(reason, "risk_blocked")
