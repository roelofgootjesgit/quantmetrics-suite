"""Map QuantLog envelope events to the Ops Console flat row contract."""

from __future__ import annotations

from typing import Any

UNK = "unknown"


def _payload(event: dict[str, Any]) -> dict[str, Any]:
    p = event.get("payload")
    return p if isinstance(p, dict) else {}


def _dc(payload: dict[str, Any]) -> dict[str, Any]:
    dc = payload.get("decision_context")
    return dc if isinstance(dc, dict) else {}


def _unk_str(v: Any) -> str:
    """Explicit ``unknown`` when envelope/string fields are missing or blank."""
    t = str(v or "").strip()
    return t if t else UNK


def normalize_event(event: dict[str, Any]) -> dict[str, Any]:
    """Flatten envelope + payload for tables, filters, CSV (handbook §6).

    ``run_id`` stays empty when absent so shard indexing / unknown-run buckets keep working.
    Other canonical strings use ``unknown`` when missing.
    """
    pl = _payload(event)
    dc = _dc(pl)

    et_raw = event.get("event_type")
    et = _unk_str(et_raw) if et_raw is not None else UNK

    symbol_raw = event.get("symbol") if event.get("symbol") is not None else pl.get("symbol")
    symbol_s = _unk_str(symbol_raw)

    sess_raw = pl.get("session") if pl.get("session") is not None else dc.get("session")
    session_s = _unk_str(sess_raw)

    reg_raw = pl.get("regime") if pl.get("regime") is not None else dc.get("regime")
    regime_s = _unk_str(reg_raw)

    decision = ""
    reason_code = ""
    confidence = 0.0

    if et == "trade_action":
        decision = str(pl.get("decision") or "")
        rr = str(pl.get("reason") or "").strip()
        if decision == "NO_ACTION":
            reason_code = rr if rr else UNK
        else:
            reason_code = rr if rr else ""
        confidence = float(pl.get("confidence") or 0.0)
    elif et == "risk_guard_decision":
        decision = str(pl.get("decision") or "")
        rr = str(pl.get("reason") or "").strip()
        reason_code = rr if rr else UNK
    elif et == "signal_filtered":
        decision = "FILTERED"
        fr = str(pl.get("filter_reason") or pl.get("raw_reason") or "").strip()
        reason_code = fr if fr else UNK
    elif et in {"signal_evaluated", "signal_detected"}:
        confidence = float(pl.get("confidence") or 0.0)
        if et == "signal_evaluated":
            es = str(pl.get("eval_stage") or "").strip()
            decision = es if es else UNK
    elif et == "trade_executed":
        decision = str(pl.get("direction") or "EXECUTED")

    order_ref = str(pl.get("order_ref") or event.get("order_ref") or "")
    rid = str(event.get("run_id") or "").strip()

    return {
        "timestamp_utc": str(event.get("timestamp_utc") or ""),
        "run_id": rid,
        "event_type": et,
        "symbol": symbol_s,
        "session": session_s,
        "regime": regime_s,
        "decision": decision,
        "reason_code": reason_code,
        "confidence": confidence,
        "source_system": str(event.get("source_system") or ""),
        "order_ref": order_ref,
        "_trace_id": str(event.get("trace_id") or ""),
        "_severity": str(event.get("severity") or ""),
        "_raw": event,
    }
