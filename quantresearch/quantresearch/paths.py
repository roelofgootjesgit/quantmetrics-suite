"""Resolve QuantResearch repo paths (data live next to the package)."""

from __future__ import annotations

import os
from pathlib import Path


def repo_root() -> Path:
    """Root of the quantresearch repository (contains registry/, schemas/, ...)."""
    env = os.environ.get("QUANTRESEARCH_ROOT")
    if env:
        return Path(env).resolve()
    return Path(__file__).resolve().parent.parent


def registry_dir() -> Path:
    return repo_root() / "registry"


def comparisons_dir() -> Path:
    return repo_root() / "comparisons"


def research_logs_dir() -> Path:
    return repo_root() / "research_logs"


def templates_dir() -> Path:
    return repo_root() / "templates"


def schemas_dir() -> Path:
    return repo_root() / "schemas"


def experiments_dir() -> Path:
    """Per-experiment human artifacts: hypothesis, plan, decision (see ``schemas/experiment_bundle.schema.json``)."""
    return repo_root() / "experiments"
