"""Helpers for reading QuantLog JSONL events."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


@dataclass(slots=True, frozen=True)
class RawEventLine:
    path: Path
    line_number: int
    raw: str
    parsed: dict[str, Any] | None
    parse_error: str | None = None


def iter_jsonl_file(path: Path) -> Iterable[RawEventLine]:
    with path.open("r", encoding="utf-8") as handle:
        for idx, line in enumerate(handle, start=1):
            raw = line.strip()
            if not raw:
                continue
            try:
                parsed = json.loads(raw)
                if not isinstance(parsed, dict):
                    raise ValueError("json value is not an object")
                yield RawEventLine(path=path, line_number=idx, raw=raw, parsed=parsed)
            except Exception as exc:  # noqa: BLE001
                yield RawEventLine(
                    path=path,
                    line_number=idx,
                    raw=raw,
                    parsed=None,
                    parse_error=str(exc),
                )


def discover_jsonl_files(path: Path) -> list[Path]:
    path = path.expanduser()
    if not path.exists():
        raise FileNotFoundError(
            f"QuantLog path does not exist: {path}. "
            "Pass a real directory (e.g. data/quantlog_events/2026-04-12) or a .jsonl file — "
            "not a placeholder like '...'."
        )
    if path.is_file():
        return [path]
    return sorted(path.rglob("*.jsonl"))

