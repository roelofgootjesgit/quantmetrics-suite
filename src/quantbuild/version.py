"""QuantBuild package version and optional git revision (for Telegram / ops)."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

__version__ = "1.0.0"


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def git_revision_short() -> str:
    env_rev = os.environ.get("QUANTBUILD_GIT_REVISION", "").strip()
    if env_rev:
        return env_rev
    root = repo_root()
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if proc.returncode == 0 and (proc.stdout or "").strip():
            return proc.stdout.strip()
    except OSError:
        pass
    return "unknown"
