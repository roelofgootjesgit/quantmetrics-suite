"""Rules-based “no trade” narrative — no AI (Sprint A)."""

from __future__ import annotations

from collections import Counter
from typing import Any


def _pct(part: int, whole: int) -> float:
    if whole <= 0:
        return 0.0
    return round(100.0 * part / whole, 1)


def regime_dominance_among_evaluated(rows: list[dict[str, Any]]) -> tuple[str | None, float]:
    """Return (top_regime, pct_of_evaluated_signals) using ``signal_evaluated`` rows only."""
    regimes: Counter[str] = Counter()
    for row in rows:
        if row.get("event_type") != "signal_evaluated":
            continue
        reg = (row.get("regime") or "").strip()
        if not reg or reg == "unknown":
            regimes["unknown"] += 1
        else:
            regimes[reg] += 1
    total = sum(regimes.values())
    if not regimes or total == 0:
        return None, 0.0
    top, cnt = regimes.most_common(1)[0]
    return top, _pct(cnt, total)


def build_no_trade_lines(
    *,
    summary: dict[str, Any],
    rows: list[dict[str, Any]],
    scan: dict[str, Any] | None,
    cap_hit: bool,
    merged_reason_counts: dict[str, int] | None = None,
    total_entries: int | None = None,
) -> list[str]:
    """
    Produce short bullet lines for Daily / Breakdown pages.

    ``scan`` optional: full JSONL stats (true last/first timestamps, parse rate).
    """
    lines: list[str] = []

    by_reason = merged_reason_counts if merged_reason_counts else (summary.get("by_reason") or {})
    total_reason = sum(by_reason.values())

    if by_reason and total_reason > 0:
        top_reason = max(by_reason.items(), key=lambda kv: kv[1])[0]
        pct = _pct(by_reason[top_reason], total_reason)
        lines.append(f"Most common blocker: **{top_reason}** ({pct}% of coded NO_ACTION/filter rows).")

    entries = int(total_entries if total_entries is not None else summary.get("entries") or 0)
    if entries == 0:
        lines.append("No **trade_executed** entries detected in this loaded slice.")
    else:
        lines.append(f"**{entries}** trade_executed event(s) in this slice.")

    top_reg, share = regime_dominance_among_evaluated(rows)
    n_eval = sum(1 for r in rows if r.get("event_type") == "signal_evaluated")
    if top_reg is not None and n_eval > 0:
        lines.append(
            f"Regime **{top_reg}** appeared on **{share}%** of `signal_evaluated` rows "
            f"({n_eval} evaluated in cap)."
        )

    last_from_cap = _max_ts_from_rows(rows)
    if scan and scan.get("last_timestamp_utc"):
        lines.append(
            f"System active until **{scan['last_timestamp_utc']}** UTC (last timestamp in JSONL files)."
        )
    elif last_from_cap:
        lines.append(f"Latest event in loaded cap slice: **{last_from_cap}** UTC.")

    if cap_hit:
        lines.append(
            "_No-trade explainer truncated — only the first normalized events up to the "
            "explainer cap are reflected here (regime lines and cap-window wording)._"
        )

    first_ts = scan.get("first_timestamp_utc") if scan else None
    last_disk = scan.get("last_timestamp_utc") if scan else None
    if first_ts and last_disk and first_ts != last_disk:
        lines.append(f"Raw JSONL window: **{first_ts}** → **{last_disk}** UTC.")

    return lines


def _max_ts_from_rows(rows: list[dict[str, Any]]) -> str | None:
    ts = [str(r.get("timestamp_utc") or "").strip() for r in rows]
    ts = [t for t in ts if t]
    return max(ts) if ts else None
