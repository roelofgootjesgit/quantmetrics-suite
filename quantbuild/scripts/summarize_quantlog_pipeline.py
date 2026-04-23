#!/usr/bin/env python3
"""Summarize QuantLog JSONL pipeline events (signal_detected / signal_filtered / trade_executed).

Usage:
  python scripts/summarize_quantlog_pipeline.py path/to/quantbuild.jsonl
  python scripts/summarize_quantlog_pipeline.py data/quantlog_events_demo_loose/2026-04-12

If a directory is given, uses the first quantbuild.jsonl found under it (non-recursive).
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path


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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path, help="JSONL file or day directory")
    parser.add_argument(
        "--trades",
        type=int,
        default=5,
        help="Max trade_executed rows to print (default 5)",
    )
    args = parser.parse_args()
    path = _resolve_jsonl_path(args.path.resolve())

    counts: Counter[str] = Counter()
    filter_reasons: Counter[str] = Counter()
    trades: list[dict] = []

    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            et = str(ev.get("event_type", ""))
            counts[et] += 1
            payload = ev.get("payload") or {}
            if et == "signal_filtered":
                fr = payload.get("filter_reason") or payload.get("reason") or "unknown"
                filter_reasons[str(fr)] += 1
            if et == "trade_executed":
                trades.append(
                    {
                        "trade_id": payload.get("trade_id"),
                        "direction": payload.get("direction"),
                        "signal_id": payload.get("signal_id"),
                        "regime": payload.get("regime"),
                    }
                )

    print(f"File: {path}")
    print()
    print("Event counts:")
    for k in sorted(counts.keys()):
        print(f"  {k}: {counts[k]}")
    sd = counts.get("signal_detected", 0)
    sf = counts.get("signal_filtered", 0)
    te = counts.get("trade_executed", 0)
    print()
    print(f"Funnel: {sd} signal_detected -> {sf} signal_filtered -> {te} trade_executed")
    print()
    print("Top filter_reason (signal_filtered):")
    for reason, n in filter_reasons.most_common(10):
        print(f"  {n:5d}  {reason}")
    print()
    print(f"First {args.trades} trade_executed:")
    for row in trades[: args.trades]:
        print(f"  {row}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except FileNotFoundError as e:
        print(e, file=sys.stderr)
        raise SystemExit(1)
