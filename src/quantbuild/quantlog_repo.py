"""Locate QuantLog repository for subprocess CLI (validate-events, etc.)."""

from __future__ import annotations

import os
from pathlib import Path


def quantbuild_project_root() -> Path:
    """Root of quantbuildv1 (contains ``src/``, ``tests/``, ``configs/``)."""
    return Path(__file__).resolve().parents[2]


def resolve_quantlog_repo_path() -> Path | None:
    """Path to QuantLog clone with ``src/quantlog``, or ``None`` if not found."""
    env = os.environ.get("QUANTLOG_REPO_PATH", "").strip()
    if env:
        p = Path(env)
        if (p / "src" / "quantlog").is_dir():
            return p
        return None
    candidates = [
        Path("/opt/quantbuild/quantlogv1"),
        quantbuild_project_root().parent / "quantlogv1",
    ]
    for p in candidates:
        if (p / "src" / "quantlog").is_dir():
            return p
    return None


def quantlog_pythonpath_prefix(repo: Path) -> str:
    return str((repo / "src").resolve())
