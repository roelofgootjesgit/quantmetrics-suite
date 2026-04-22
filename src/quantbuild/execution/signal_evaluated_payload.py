"""Central ``signal_evaluated`` payload construction (P0 SPRINT 1–2).

All QuantBuild emitters should use :func:`build_signal_evaluated_payload` so
session, setup_type, regime, and decision_cycle_id stay consistent in the payload
(analytics reads payload; envelope still carries correlation IDs).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class DecisionCycleContext:
    """Per-cycle correlation bundle (SPRINT 2). Pass through the decision pipeline."""

    decision_cycle_id: str
    trace_id: str
    session: str
    regime: Optional[str] = None
    setup_type: str = "sqe"


def merge_decision_context_blueprint(
    payload: Dict[str, Any],
    *,
    decision_context: Optional[Dict[str, Any]],
    regime: Optional[str],
) -> None:
    """Fill blueprint fields from ``decision_context`` (setdefault; no blind overwrites)."""
    if payload.get("signal_type") == "sqe_entry":
        payload.setdefault("setup_type", "sqe")
    dc = decision_context or {}
    sess = dc.get("session")
    if sess is not None:
        payload.setdefault("session", str(sess))
    eff_regime = regime if regime is not None else dc.get("regime")
    if eff_regime is not None:
        payload.setdefault("regime", str(eff_regime) if eff_regime not in ("", None) else "none")
    cc = dc.get("combo_active_modules_count")
    if cc is not None:
        try:
            payload.setdefault("combo_count", int(cc))
        except (TypeError, ValueError):
            pass
    pat = dc.get("price_at_signal")
    if pat is not None:
        try:
            payload.setdefault("price_at_signal", float(pat))
        except (TypeError, ValueError):
            pass
    spr = dc.get("spread_pips")
    if spr is not None:
        try:
            payload.setdefault("spread", float(spr))
        except (TypeError, ValueError):
            pass
    if payload.get("signal_type") == "sqe_entry":
        if not str(payload.get("session") or "").strip():
            fallback_s = dc.get("session")
            payload["session"] = str(fallback_s) if fallback_s is not None else "unknown"
        if not str(payload.get("setup_type") or "").strip():
            payload["setup_type"] = "sqe"
        if not str(payload.get("regime") or "").strip():
            payload["regime"] = "none"


def build_signal_evaluated_payload(
    *,
    decision_cycle_id: str,
    session: str,
    regime: Optional[str],
    signal_type: str,
    signal_direction: str,
    confidence: float,
    system_mode: str,
    bypassed_by_mode: List[Any],
    setup_type: str = "sqe",
    setup: bool = True,
    eval_stage: Optional[str] = None,
    decision_context: Optional[Dict[str, Any]] = None,
    desk_extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Return a complete ``signal_evaluated`` payload dict (before QuantLog emit)."""
    dcid = str(decision_cycle_id or "").strip()
    if not dcid:
        dcid = "dc_unset"
    sess_hint = str(session or "").strip()
    regime_eff = regime if regime not in (None, "") else "none"
    payload: Dict[str, Any] = {
        "signal_type": signal_type,
        "signal_direction": signal_direction,
        "confidence": float(confidence),
        "regime": str(regime_eff),
        "setup_type": setup_type,
        "decision_cycle_id": dcid,
        "system_mode": system_mode,
        "bypassed_by_mode": list(bypassed_by_mode or []),
    }
    if sess_hint:
        payload["session"] = sess_hint
    if not setup:
        payload["setup"] = False
    if eval_stage:
        payload["eval_stage"] = eval_stage
    if decision_context is not None:
        payload["decision_context"] = decision_context
    if desk_extra:
        payload.update(desk_extra)
    merge_decision_context_blueprint(
        payload, decision_context=decision_context, regime=regime
    )
    if not str(payload.get("session") or "").strip():
        payload["session"] = "unknown"
    return payload


def assert_signal_evaluated_payload_complete(payload: Dict[str, Any]) -> None:
    """Hard invariant for SPRINT 1 (use in tests and optional strict runs)."""
    for key in (
        "session",
        "setup_type",
        "regime",
        "signal_type",
        "signal_direction",
        "confidence",
        "decision_cycle_id",
    ):
        val = payload.get(key)
        assert val is not None, f"signal_evaluated payload missing {key!r}"
        if key == "confidence":
            assert isinstance(val, (int, float)), f"confidence must be numeric, got {type(val)}"
        else:
            assert str(val).strip() != "", f"signal_evaluated payload empty {key!r}"
