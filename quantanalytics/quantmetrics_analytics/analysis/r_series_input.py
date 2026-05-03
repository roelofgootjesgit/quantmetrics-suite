"""Resolve per-trade R series from QuantLog JSONL and optional fallback JSON."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def extract_trade_closed_pnl_r(events: list[dict[str, Any]], run_id: str | None) -> list[float]:
    """Ordered ``pnl_r`` from ``trade_closed`` events (optionally filtered by ``run_id``)."""
    out: list[float] = []
    rid = str(run_id).strip() if run_id else ""
    for ev in events:
        if ev.get("event_type") != "trade_closed":
            continue
        if rid and str(ev.get("run_id", "")).strip() != rid:
            continue
        pl = ev.get("payload") if isinstance(ev.get("payload"), dict) else {}
        v = pl.get("pnl_r")
        if v is None:
            continue
        out.append(float(v))
    return out


def resolve_inference_run_id(events: list[dict[str, Any]], explicit: str | None) -> str:
    """Pick a single run_id for inference; require explicit when multiple runs are present."""
    if explicit and str(explicit).strip():
        return str(explicit).strip()
    ids: set[str] = set()
    for ev in events:
        if ev.get("event_type") != "trade_closed":
            continue
        r = str(ev.get("run_id", "")).strip()
        if r:
            ids.add(r)
    if len(ids) == 1:
        return next(iter(ids))
    if not ids:
        raise ValueError("No trade_closed events with run_id found; cannot infer run_id.")
    raise ValueError(
        f"Multiple run_id values in trade_closed events ({sorted(ids)[:5]}...); "
        "pass --run-id / QUANTMETRICS_ANALYTICS_RUN_ID."
    )


def load_r_series_from_inputs(
    events: list[dict[str, Any]],
    *,
    run_id: str,
    jsonl_paths: list[Path],
) -> tuple[list[float], str]:
    """Return (r_series, source_tag). Prefers JSONL ``trade_closed``; else sidecar ``*_trade_r_series.json``."""
    r = extract_trade_closed_pnl_r(events, run_id)
    if r:
        return r, "trade_closed_jsonl"
    for path in jsonl_paths:
        if path.is_file() and path.suffix.lower() == ".jsonl":
            sidecar = path.parent / f"{run_id}_trade_r_series.json"
            if sidecar.is_file():
                raw = json.loads(sidecar.read_text(encoding="utf-8"))
                trades = raw.get("trades") if isinstance(raw, dict) else None
                if isinstance(trades, list):
                    return [float(t["pnl_r"]) for t in trades if isinstance(t, dict) and t.get("pnl_r") is not None], (
                        "trade_r_series_json"
                    )
    return [], "none"
