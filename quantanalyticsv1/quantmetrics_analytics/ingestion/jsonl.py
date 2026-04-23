"""Load QuantLog JSONL (read-only, one JSON object per line)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Iterator


def iter_jsonl_events(path: Path) -> Iterator[tuple[int, dict[str, Any]]]:
    """
    Yield (line_number, parsed_event). Skips blank lines.
    Invalid JSON lines are logged to stderr and skipped.
    """
    with path.open(encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                obj = json.loads(stripped)
            except json.JSONDecodeError as exc:
                print(
                    f"[quantmetrics_analytics] skip line {line_no} in {path}: {exc}",
                    file=sys.stderr,
                )
                continue
            if not isinstance(obj, dict):
                print(
                    f"[quantmetrics_analytics] skip line {line_no} in {path}: not an object",
                    file=sys.stderr,
                )
                continue
            yield line_no, obj


def load_events_from_paths(paths: list[Path]) -> list[dict[str, Any]]:
    """Load all events from paths (deterministic order: sorted paths, then line order)."""
    events: list[dict[str, Any]] = []
    for path in sorted(paths):
        if not path.is_file():
            print(f"[quantmetrics_analytics] skip missing file: {path}", file=sys.stderr)
            continue
        for _, ev in iter_jsonl_events(path):
            events.append(ev)
    return events
