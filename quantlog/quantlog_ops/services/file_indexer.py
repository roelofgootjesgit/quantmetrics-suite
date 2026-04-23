"""Discover QuantLog JSONL days and runs (handbook §7.1)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from quantlog.events.io import discover_jsonl_files, iter_jsonl_file

_DATE_DIR = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def list_date_dirs(root: Path) -> list[str]:
    """Sorted ISO dates present under ``root``."""
    root = root.expanduser().resolve()
    if not root.is_dir():
        return []
    dates: list[str] = []
    for child in sorted(root.iterdir()):
        if child.is_dir() and _DATE_DIR.match(child.name):
            dates.append(child.name)
    return dates


def index_day(day_path: Path) -> dict[str, Any]:
    """
    Scan one day's JSONL files and group by ``run_id``.

    Returns ``{"date": str, "runs": [{"run_id", "path", "files"}, ...]}``.
    """
    day_path = day_path.expanduser().resolve()
    date_key = day_path.name if _DATE_DIR.match(day_path.name) else day_path.name

    run_files: dict[str, set[Path]] = {}
    run_representative: dict[str, Path] = {}

    files = discover_jsonl_files(day_path)
    for jsonl_path in files:
        for raw in iter_jsonl_file(jsonl_path):
            if raw.parsed is None:
                continue
            rid = str(raw.parsed.get("run_id") or "").strip() or "(unknown_run)"
            if rid not in run_files:
                run_files[rid] = set()
                run_representative[rid] = jsonl_path
            run_files[rid].add(jsonl_path)

    runs_out: list[dict[str, Any]] = []
    for rid in sorted(run_files.keys()):
        paths_sorted = sorted(run_files[rid], key=lambda p: str(p))
        runs_out.append(
            {
                "run_id": rid,
                "path": str(run_representative.get(rid) or paths_sorted[0]),
                "files": [str(p) for p in paths_sorted],
            }
        )

    return {"date": date_key, "runs": runs_out}


def index_root(root: Path) -> list[dict[str, Any]]:
    """Full tree: one entry per date under ``root``."""
    root = root.expanduser().resolve()
    out: list[dict[str, Any]] = []
    for d in list_date_dirs(root):
        day = root / d
        out.append(index_day(day))
    return out
