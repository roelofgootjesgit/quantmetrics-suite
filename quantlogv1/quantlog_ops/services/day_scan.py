"""Full-pass JSONL stats for a day (timestamps, parse failures) — cached at UI layer."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from quantlog.events.io import discover_jsonl_files, iter_jsonl_file


def scan_day_jsonl_stats(day_path: Path) -> dict[str, Any]:
    """
    Scan every non-empty line in the day's JSONL shard(s).

    Returns parse-failure counts and min/max ``timestamp_utc`` among successfully
    parsed objects (ISO strings compared lexicographically — OK for QuantLog UTC).
    """
    day_path = day_path.expanduser().resolve()
    files = discover_jsonl_files(day_path)

    non_empty_lines = 0
    parse_failures = 0
    min_ts: str | None = None
    max_ts: str | None = None

    for fp in sorted(files, key=lambda p: str(p)):
        for raw in iter_jsonl_file(fp):
            line = raw.raw.strip() if raw.raw else ""
            if not line:
                continue
            non_empty_lines += 1
            if raw.parsed is None:
                parse_failures += 1
                continue
            ts = raw.parsed.get("timestamp_utc")
            if not isinstance(ts, str) or not ts.strip():
                continue
            ts = ts.strip()
            if min_ts is None or ts < min_ts:
                min_ts = ts
            if max_ts is None or ts > max_ts:
                max_ts = ts

    pct_parse_fallback = (
        100.0 * parse_failures / non_empty_lines if non_empty_lines else 0.0
    )

    return {
        "non_empty_lines": non_empty_lines,
        "parse_failures": parse_failures,
        "pct_parse_fallback": round(pct_parse_fallback, 2),
        "first_timestamp_utc": min_ts,
        "last_timestamp_utc": max_ts,
    }
