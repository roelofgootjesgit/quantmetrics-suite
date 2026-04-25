"""Locate QuantLog repository for subprocess CLI (validate-events, etc.)."""

from __future__ import annotations

import os
from pathlib import Path

from src.quantbuild.suite_layout import canonical_quantlog_repo_path


def quantbuild_project_root() -> Path:
    """Root of quantbuild (contains ``src/``, ``tests/``, ``configs/``)."""
    return Path(__file__).resolve().parents[2]


def resolve_quantlog_repo_path() -> Path | None:
    """Path to QuantLog clone with ``src/quantlog``, or ``None`` if not found."""
    for env_key in ("QUANTLOG_REPO_PATH", "QUANTLOG_ROOT"):
        raw = os.environ.get(env_key, "").strip()
        if not raw:
            continue
        p = Path(raw)
        if (p / "src" / "quantlog").is_dir():
            return p.resolve()
    try:
        p = canonical_quantlog_repo_path()
    except Exception:
        return None
    if (p / "src" / "quantlog").is_dir():
        return p
    return None


def quantlog_pythonpath_prefix(repo: Path) -> str:
    return str((repo / "src").resolve())
