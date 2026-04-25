#!/usr/bin/env python3
"""Fail CI when legacy *v1 local path segments are present."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ALLOWED_EXTENSIONS = {
    ".py",
    ".yml",
    ".yaml",
    ".json",
    ".toml",
    ".ini",
    ".cfg",
    ".conf",
    ".env",
    ".example",
    ".ps1",
    ".sh",
}
SKIP_DIRS = {".git", ".venv", "__pycache__", ".pytest_cache", "site-packages"}
LEGACY_SEGMENT = re.compile(
    r"(?i)(^|[\\/])(quant(?:build|bridge|log|analytics)v1)(?=[\\/]|$)"
)


def _iter_files() -> list[Path]:
    files: list[Path] = []
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.suffix.lower() in ALLOWED_EXTENSIONS or path.name.endswith(".env.example"):
            files.append(path)
    return files


def main() -> int:
    failures: list[str] = []
    for path in _iter_files():
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for idx, line in enumerate(text.splitlines(), start=1):
            if LEGACY_SEGMENT.search(line):
                rel = path.relative_to(ROOT).as_posix()
                failures.append(f"{rel}:{idx}: {line.strip()}")

    if failures:
        print("Legacy *v1 path references found. Use canonical suite paths instead.", file=sys.stderr)
        for row in failures:
            print(row, file=sys.stderr)
        return 1
    print("No legacy *v1 path references found.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
