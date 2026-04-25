"""Canonical QuantMetrics suite layout validation utilities."""

from __future__ import annotations

import os
from pathlib import Path

from src.quantbuild.config import quantbuild_repo_root

EXPECTED_REPOS = (
    "quantbuild",
    "quantbridge",
    "quantlog",
    "quantanalytics",
    "quantmetrics_os",
)


class SuiteLayoutError(RuntimeError):
    """Raised when the repository layout/env does not match suite policy."""


def _norm(path: Path) -> Path:
    return path.expanduser().resolve()


def _read_env_path(name: str) -> Path | None:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return None
    return _norm(Path(raw))


def resolve_suite_root() -> Path:
    """Resolve canonical suite root from environment, fail-fast when missing."""
    explicit = _read_env_path("QUANTMETRICS_SUITE_ROOT")
    if explicit is not None:
        return explicit

    qm_root = _read_env_path("QUANTMETRICS_OS_ROOT")
    if qm_root is not None:
        return qm_root.parent

    raise SuiteLayoutError(
        "Missing suite root. Set QUANTMETRICS_SUITE_ROOT or QUANTMETRICS_OS_ROOT "
        "(expected under .../quantmetrics-suite)."
    )


def canonical_repo_path(repo_name: str) -> Path:
    """Return canonical path for a sibling repository under suite root."""
    return (resolve_suite_root() / repo_name).resolve()


def canonical_quantbridge_src_path() -> Path:
    return (canonical_repo_path("quantbridge") / "src").resolve()


def canonical_quantlog_repo_path() -> Path:
    return canonical_repo_path("quantlog")


def validate_suite_layout() -> dict[str, str]:
    """Validate suite-root consistency and canonical sibling paths.

    Returns a mapping with canonical absolute paths when successful.
    """
    suite_root = resolve_suite_root()
    if not suite_root.is_dir():
        raise SuiteLayoutError(f"Suite root does not exist: {suite_root}")

    qb_root = _norm(quantbuild_repo_root())
    expected_qb = (suite_root / "quantbuild").resolve()
    if qb_root != expected_qb:
        raise SuiteLayoutError(
            f"QuantBuild root mismatch. current={qb_root} expected={expected_qb}"
        )

    missing = [name for name in EXPECTED_REPOS if not (suite_root / name).is_dir()]
    if missing:
        raise SuiteLayoutError(
            f"Suite layout incomplete under {suite_root}. Missing repos: {', '.join(missing)}"
        )

    canonical_qm = (suite_root / "quantmetrics_os").resolve()
    env_qm = _read_env_path("QUANTMETRICS_OS_ROOT")
    if env_qm is not None and env_qm != canonical_qm:
        raise SuiteLayoutError(
            f"QUANTMETRICS_OS_ROOT mismatch. current={env_qm} expected={canonical_qm}"
        )

    canonical_ql = (suite_root / "quantlog").resolve()
    for env_name in ("QUANTLOG_REPO_PATH", "QUANTLOG_ROOT"):
        env_val = _read_env_path(env_name)
        if env_val is not None and env_val != canonical_ql:
            raise SuiteLayoutError(
                f"{env_name} mismatch. current={env_val} expected={canonical_ql}"
            )

    canonical_qb_src = (suite_root / "quantbridge" / "src").resolve()
    env_qb_src = _read_env_path("QUANTBRIDGE_SRC_PATH")
    if env_qb_src is not None and env_qb_src != canonical_qb_src:
        raise SuiteLayoutError(
            f"QUANTBRIDGE_SRC_PATH mismatch. current={env_qb_src} expected={canonical_qb_src}"
        )

    env_qa_out = _read_env_path("QUANTMETRICS_ANALYTICS_OUTPUT_DIR")
    canonical_qa_out = (suite_root / "quantanalytics" / "output_rapport").resolve()
    if env_qa_out is not None and env_qa_out != canonical_qa_out:
        raise SuiteLayoutError(
            "QUANTMETRICS_ANALYTICS_OUTPUT_DIR mismatch. "
            f"current={env_qa_out} expected={canonical_qa_out}"
        )

    return {
        "suite_root": str(suite_root),
        "quantbuild_root": str(expected_qb),
        "quantmetrics_os_root": str(canonical_qm),
        "quantlog_root": str(canonical_ql),
        "quantbridge_src_path": str(canonical_qb_src),
        "quantanalytics_output_dir": str(canonical_qa_out),
    }
