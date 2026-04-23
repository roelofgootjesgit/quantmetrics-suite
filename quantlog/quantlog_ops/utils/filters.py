"""Filter normalized event rows (handbook §8.3)."""

from __future__ import annotations

from typing import Any, Iterable


def apply_filters(
    rows: Iterable[dict[str, Any]],
    *,
    event_type: str | None = None,
    decision: str | None = None,
    symbol: str | None = None,
    regime: str | None = None,
) -> list[dict[str, Any]]:
    """Return rows matching all non-empty filter strings (substring match)."""
    et_f = (event_type or "").strip().lower()
    dec_f = (decision or "").strip().lower()
    sym_f = (symbol or "").strip().upper()
    reg_f = (regime or "").strip().lower()

    out: list[dict[str, Any]] = []
    for row in rows:
        if et_f and et_f not in (row.get("event_type") or "").lower():
            continue
        if dec_f and dec_f not in (row.get("decision") or "").lower():
            continue
        if sym_f and sym_f not in (row.get("symbol") or "").upper():
            continue
        if reg_f and reg_f not in (row.get("regime") or "").lower():
            continue
        out.append(row)
    return out
