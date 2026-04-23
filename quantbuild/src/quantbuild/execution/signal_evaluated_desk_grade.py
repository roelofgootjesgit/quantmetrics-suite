"""Desk-grade optional fields for QuantLog ``signal_evaluated`` (QuantBuild → QuantLog v1).

Aligned with docs/QUANTBUILD_LOGGING_UPGRADE_DATA_COLLECTION.md Phase 1–2 optional payload.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

_GATE_ORDER: Tuple[str, ...] = (
    "session_gate",
    "regime_gate",
    "structure_gate",
    "liquidity_gate",
    "trigger_gate",
    "same_bar_guard",
    "risk_gate",
)


def _empty_gate_summary() -> Dict[str, str]:
    return {k: "not_reached" for k in _GATE_ORDER}


def _split_long_short(
    decision_context: Optional[Dict[str, Any]],
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    if not decision_context:
        return {}, {}
    if "long" in decision_context or "short" in decision_context:
        lo = decision_context.get("long")
        sh = decision_context.get("short")
        return (
            lo if isinstance(lo, dict) else {},
            sh if isinstance(sh, dict) else {},
        )
    direction = decision_context.get("direction")
    if direction == "LONG":
        return decision_context, {}
    if direction == "SHORT":
        return {}, decision_context
    return {}, {}


def _modules_triplet(ctx: Dict[str, Any]) -> Tuple[bool, bool, bool]:
    return (
        bool(ctx.get("structure_ok")),
        bool(ctx.get("liquidity_pillar_ok")),
        bool(ctx.get("trigger_ok")),
    )


def _modules_payload(struct: bool, liq: bool, trig: bool) -> Dict[str, bool]:
    return {"structure": struct, "liquidity": liq, "trigger": trig}


def _missing_labels(struct: bool, liq: bool, trig: bool) -> List[str]:
    out: List[str] = []
    if not struct:
        out.append("structure")
    if not liq:
        out.append("liquidity")
    if not trig:
        out.append("trigger")
    return out


def build_desk_grade_payload(
    *,
    eval_stage: Optional[str],
    decision_context: Optional[Dict[str, Any]],
    setup: bool,
    direction: str,
    confidence: float,
    same_bar_skip_count_for_bar: int,
    previous_eval_stage_on_bar: Optional[str],
    poll_ts: datetime,
    bar_ts_str: Optional[str],
    new_bar_detected: bool,
) -> Dict[str, Any]:
    """Return optional QuantLog payload keys (flat dict)."""
    poll_iso = poll_ts.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    out: Dict[str, Any] = {
        "poll_ts": poll_iso,
        "new_bar_detected": bool(new_bar_detected),
    }
    if bar_ts_str:
        out["bar_ts"] = bar_ts_str

    stage = eval_stage or ""
    out["same_bar_guard_triggered"] = stage == "same_bar_already_processed"
    if stage == "same_bar_already_processed":
        out["same_bar_guard_reason"] = "last_processed_bar_ts_matches_latest_bar_ts"

    out["same_bar_skip_count_for_bar"] = int(max(0, same_bar_skip_count_for_bar))

    if previous_eval_stage_on_bar:
        out["previous_eval_stage_on_bar"] = previous_eval_stage_on_bar

    long_c, short_c = _split_long_short(decision_context)

    gs = _empty_gate_summary()
    primary: Optional[str] = None
    secondary: Optional[str] = None
    eval_path: List[str] = []

    if stage == "same_bar_already_processed":
        gs["session_gate"] = "pass"
        gs["regime_gate"] = "pass"
        gs["structure_gate"] = "not_reached"
        gs["liquidity_gate"] = "not_reached"
        gs["trigger_gate"] = "not_reached"
        gs["same_bar_guard"] = "fail"
        gs["risk_gate"] = "not_reached"
        primary = "same_bar_guard"
        eval_path = ["session_gate", "regime_gate", "same_bar_guard"]

    elif stage == "regime_block":
        gs["session_gate"] = "pass"
        gs["regime_gate"] = "fail"
        for k in ("structure_gate", "liquidity_gate", "trigger_gate", "same_bar_guard", "risk_gate"):
            gs[k] = "not_reached"
        primary = "regime_gate"
        eval_path = ["session_gate", "regime_gate"]

    elif stage in {"outside_killzone", "time_filter_block"}:
        gs["session_gate"] = "fail"
        for k in _GATE_ORDER[1:]:
            gs[k] = "not_reached"
        primary = "session_gate"
        eval_path = ["session_gate"]

    elif stage in {"position_limit_block", "daily_loss_block"}:
        gs["session_gate"] = "pass"
        gs["regime_gate"] = "pass"
        for k in ("structure_gate", "liquidity_gate", "trigger_gate", "same_bar_guard"):
            gs[k] = "not_reached"
        gs["risk_gate"] = "fail"
        primary = "risk_gate"
        eval_path = ["session_gate", "regime_gate", "risk_gate"]

    elif stage == "bars_missing":
        gs["session_gate"] = "pass"
        gs["regime_gate"] = "pass"
        gs["structure_gate"] = "fail"
        for k in ("liquidity_gate", "trigger_gate", "same_bar_guard", "risk_gate"):
            gs[k] = "not_reached"
        primary = "structure_gate"
        eval_path = ["session_gate", "regime_gate", "structure_gate"]

    elif stage == "no_entry_signal" and (long_c or short_c):
        gs["session_gate"] = "pass"
        gs["regime_gate"] = "pass"
        ls, lt, lz = _modules_triplet(long_c)
        ss, st, sz = _modules_triplet(short_c)
        st_ok = ls or ss
        liq_ok = lt or st
        tr_ok = lz or sz
        gs["structure_gate"] = "pass" if st_ok else "fail"
        gs["liquidity_gate"] = "pass" if liq_ok else "fail"
        gs["trigger_gate"] = "pass" if tr_ok else "fail"
        gs["same_bar_guard"] = "pass"
        gs["risk_gate"] = "pass"

        if not st_ok:
            primary = "structure_gate"
            eval_path = ["session_gate", "regime_gate", "structure_gate"]
        elif not liq_ok:
            primary = "liquidity_gate"
            if not tr_ok:
                secondary = "trigger_gate"
            eval_path = ["session_gate", "regime_gate", "structure_gate", "liquidity_gate"]
        elif not tr_ok:
            primary = "trigger_gate"
            eval_path = [
                "session_gate",
                "regime_gate",
                "structure_gate",
                "liquidity_gate",
                "trigger_gate",
            ]
        else:
            gs["trigger_gate"] = "fail"
            primary = "trigger_gate"
            eval_path = [
                "session_gate",
                "regime_gate",
                "structure_gate",
                "liquidity_gate",
                "trigger_gate",
            ]

        score_l = sum((ls, lt, lz))
        score_s = sum((ss, st, sz))
        best_side = "long" if score_l >= score_s else "short"
        best_ctx = long_c if score_l >= score_s else short_c

        out["closest_to_entry_side"] = best_side
        out["near_entry_score"] = round(max(score_l, score_s) / 3.0, 4)
        out["entry_distance_long"] = 3 - score_l
        out["entry_distance_short"] = 3 - score_s

        out["modules_long"] = _modules_payload(ls, lt, lz)
        out["modules_short"] = _modules_payload(ss, st, sz)
        out["combo_active_modules_count_long"] = score_l
        out["combo_active_modules_count_short"] = score_s
        out["missing_modules_long"] = _missing_labels(ls, lt, lz)
        out["missing_modules_short"] = _missing_labels(ss, st, sz)

        combo_min = best_ctx.get("combo_min_modules")
        combo_ct = best_ctx.get("combo_active_modules_count")
        if isinstance(combo_min, int) and isinstance(combo_ct, int):
            out["setup_candidate"] = combo_ct > 0 and combo_ct < combo_min and bool(best_ctx.get("structure_ok"))
            out["candidate_strength"] = round(min(1.0, combo_ct / max(1, combo_min)), 4)
            out["candidate_reason"] = (
                "structure_present_combo_below_min" if out["setup_candidate"] else "no_viable_candidate"
            )
            out["entry_ready"] = bool(best_ctx.get("entry_signal"))

        tsnap: Dict[str, Any] = {}
        if isinstance(combo_min, int):
            tsnap["min_combo_required"] = combo_min
        lb = best_ctx.get("combo_lookback_bars")
        if isinstance(lb, int):
            tsnap["lookback_bars"] = lb
        if tsnap:
            out["threshold_snapshot"] = tsnap

    elif stage == "no_entry_signal":
        gs["session_gate"] = "pass"
        gs["regime_gate"] = "pass"
        gs["structure_gate"] = "fail"
        for k in ("liquidity_gate", "trigger_gate", "same_bar_guard", "risk_gate"):
            gs[k] = "not_reached"
        primary = "structure_gate"
        eval_path = ["session_gate", "regime_gate", "structure_gate"]

    elif setup and direction in {"LONG", "SHORT"} and confidence > 0:
        for k in _GATE_ORDER:
            gs[k] = "pass"

    else:
        gs["session_gate"] = "pass"
        gs["regime_gate"] = "pass"
        for k in _GATE_ORDER[2:]:
            gs[k] = "not_reached"

    out["gate_summary"] = gs
    if primary:
        out["blocked_by_primary_gate"] = primary
    if secondary:
        out["blocked_by_secondary_gate"] = secondary
    if eval_path:
        out["evaluation_path"] = eval_path

    return out
