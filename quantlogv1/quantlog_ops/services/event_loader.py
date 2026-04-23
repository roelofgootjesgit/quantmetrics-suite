"""Lazy JSONL loading with caps (handbook §7.2, §9)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterator

from quantlog.events.io import discover_jsonl_files, iter_jsonl_file

from utils.parser import normalize_event


def iter_normalized_events(
    paths: list[Path | str],
    *,
    run_id: str | None = None,
    max_events: int = 10_000,
) -> Iterator[dict[str, Any]]:
    """
    Yield normalized rows from JSONL paths until ``max_events`` reached.

    Order: sorted file paths, line order within files. Fault-tolerant per line.
    """
    rid_filter = (run_id or "").strip()
    collected = 0
    sorted_paths = sorted({Path(p).expanduser().resolve() for p in paths})

    for fp in sorted_paths:
        if collected >= max_events:
            break
        if not fp.is_file():
            continue
        for raw in iter_jsonl_file(fp):
            if collected >= max_events:
                break
            if raw.parsed is None:
                continue
            if rid_filter and str(raw.parsed.get("run_id") or "").strip() != rid_filter:
                continue
            row = normalize_event(raw.parsed)
            row["_raw"] = raw.parsed
            row["_source_file"] = str(fp)
            row["_line"] = raw.line_number
            collected += 1
            yield row


def load_day_events(
    day_path: Path,
    *,
    run_id: str | None = None,
    max_events: int = 10_000,
) -> list[dict[str, Any]]:
    """All JSONL under a day directory, optionally filtered by run."""
    day_path = day_path.expanduser().resolve()
    files = discover_jsonl_files(day_path)
    return list(
        iter_normalized_events(files, run_id=run_id, max_events=max_events)
    )
