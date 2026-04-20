#!/usr/bin/env python3
"""Daily rollup for Edge Unlock Plan §1.6 — QuantLog JSONL review.

Reads a ``quantbuild.jsonl`` (or day directory) and prints:
  total signal_detected, trade_action ENTER / NO_ACTION, signal→entry ratio,
  top NO_ACTION reasons, risk_guard_decision counts, session/regime mix.

Usage:
  python scripts/edge_unlock_daily_review.py path/to/quantbuild.jsonl
  python scripts/edge_unlock_daily_review.py data/quantlog_events_live/2026-04-19/
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict


def _resolve_jsonl_path(p: Path) -> Path:
    if p.is_file() and p.suffix == ".jsonl":
        return p
    if p.is_dir():
        cand = p / "quantbuild.jsonl"
        if cand.is_file():
            return cand
        jsonls = sorted(p.glob("*.jsonl"))
        if jsonls:
            return jsonls[0]
    raise FileNotFoundError(f"No quantbuild.jsonl at {p}")


def _iso_date_from_event(ev: Dict[str, Any]) -> str:
    ts = ev.get("timestamp_utc") or ev.get("ingested_at_utc") or ""
    s = str(ts)
    if len(s) >= 10 and s[4] == "-" and s[7] == "-":
        return s[:10]
    return ""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path, help="JSONL file or day directory")
    parser.add_argument(
        "--date",
        metavar="YYYY-MM-DD",
        default=None,
        help="Only include events on this UTC calendar date (optional)",
    )
    args = parser.parse_args()
    path = _resolve_jsonl_path(args.path.resolve())

    counts: Counter[str] = Counter()
    enter_n = 0
    no_action_reasons: Counter[str] = Counter()
    guard_key: Counter[str] = Counter()
    sessions: Counter[str] = Counter()
    regimes: Counter[str] = Counter()
    modes: Counter[str] = Counter()

    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            if args.date:
                d = _iso_date_from_event(ev)
                if d and d != args.date:
                    continue

            et = str(ev.get("event_type", ""))
            counts[et] += 1
            payload = ev.get("payload") if isinstance(ev.get("payload"), dict) else {}

            sm = payload.get("system_mode")
            if isinstance(sm, str) and sm:
                modes[sm] += 1

            if et == "trade_action":
                dec = str(payload.get("decision", "")).upper()
                if dec == "ENTER":
                    enter_n += 1
                elif dec == "NO_ACTION":
                    r = str(payload.get("reason") or "unknown")
                    no_action_reasons[r] += 1
                sess = payload.get("session")
                if isinstance(sess, str) and sess:
                    sessions[sess] += 1
                reg = payload.get("regime")
                if isinstance(reg, str) and reg:
                    regimes[reg] += 1

            if et == "signal_detected":
                sess = payload.get("session")
                if isinstance(sess, str) and sess:
                    sessions[sess] += 1
                reg = payload.get("regime")
                if isinstance(reg, str) and reg:
                    regimes[reg] += 1

            if et == "risk_guard_decision":
                gn = str(payload.get("guard_name") or "unknown")
                gd = str(payload.get("decision") or "")
                guard_key[f"{gn}:{gd}"] += 1

    sd = counts.get("signal_detected", 0)
    ratio = (enter_n / sd) if sd else 0.0

    print(f"File: {path}")
    if args.date:
        print(f"Filter: UTC date == {args.date}")
    print()
    print("Event counts (selected types):")
    for k in sorted(counts.keys()):
        if k in (
            "signal_detected",
            "signal_evaluated",
            "signal_filtered",
            "trade_action",
            "trade_executed",
            "risk_guard_decision",
        ):
            print(f"  {k}: {counts[k]}")
    print()
    print(f"signal_detected: {sd}")
    print(f"trade_action ENTER: {enter_n}")
    print(f"signal → entry ratio: {ratio:.4f} ({enter_n}/{sd})")
    print()
    print("Top trade_action NO_ACTION reasons:")
    for reason, n in no_action_reasons.most_common(15):
        print(f"  {n:5d}  {reason}")
    print()
    print("risk_guard_decision:")
    for key, n in guard_key.most_common(15):
        print(f"  {n:5d}  {key}")
    print()
    print("Session mix (signal_detected + trade_action):")
    for s, n in sessions.most_common():
        print(f"  {n:5d}  {s}")
    print()
    print("Regime mix (signal_detected + trade_action):")
    for r, n in regimes.most_common():
        print(f"  {n:5d}  {r}")
    if modes:
        print()
        print("system_mode (events with payload.system_mode):")
        for m, n in modes.most_common():
            print(f"  {n:5d}  {m}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except FileNotFoundError as e:
        print(e, file=sys.stderr)
        raise SystemExit(1)
