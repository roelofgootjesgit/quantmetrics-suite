"""Optional post-run: invoke QuantAnalytics on QuantLog JSONL (default on when QuantLog ran)."""

from __future__ import annotations

import logging
import os
import subprocess  # nosec B404
import sys
from pathlib import Path
from typing import Any

from src.quantbuild.execution.quantlog_emitter import QuantLogEmitter
from src.quantbuild.quantlog_repo import quantbuild_project_root

logger = logging.getLogger(__name__)


def discover_quantanalytics_output_rapport(quantbuild_root: Path | None = None) -> Path | None:
    """Direct sibling ``../quantanalyticsv1/output_rapport`` (one parent hop only).

    Used so backtest-triggered analytics writes reports into the analytics clone that
    sits **next to** ``quantbuildv1`` under the same parent folder — not by walking up
    to arbitrary ancestors (which could match another user-wide checkout).

    For deeper monorepo layouts, set ``QUANTMETRICS_ANALYTICS_OUTPUT_DIR`` explicitly.
    """
    root = (quantbuild_root or quantbuild_project_root()).resolve()
    parent = root.parent
    if parent == root:
        return None
    qa = parent / "quantanalyticsv1"
    out = qa / "output_rapport"
    meta = qa / "pyproject.toml"
    pkg = qa / "quantmetrics_analytics"
    if not (meta.is_file() and pkg.is_dir()):
        return None
    try:
        txt = meta.read_text(encoding="utf-8")
    except OSError:
        return None
    if "quantmetrics-analytics" not in txt:
        return None
    out.mkdir(parents=True, exist_ok=True)
    return out.resolve()


def _env_auto_disabled() -> bool:
    raw = os.environ.get("QUANTMETRICS_ANALYTICS_AUTO", "1").strip().lower()
    return raw in {"0", "false", "no", "off"}


def invoke_quantanalytics_after_quantlog(
    cfg: dict[str, Any],
    ql_emitter: QuantLogEmitter | None,
) -> None:
    """Run QuantAnalytics CLI on the QuantLog tree so reports land under ``quantanalyticsv1/output_rapport``.

    Skips when: no emitter, ``quantlog.auto_analytics: false``, or
    ``QUANTMETRICS_ANALYTICS_AUTO=0``. Failures are logged but never raise (backtest result unchanged).
    """
    if ql_emitter is None:
        return
    ql_cfg = cfg.get("quantlog") or {}
    if not bool(ql_cfg.get("auto_analytics", True)):
        return
    if _env_auto_disabled():
        logger.info("QuantAnalytics post-run skipped (QUANTMETRICS_ANALYTICS_AUTO disabled).")
        return

    base = Path(ql_emitter.base_path).resolve()
    if not base.is_dir():
        logger.warning("QuantAnalytics post-run skipped: quantlog base_path is not a directory: %s", base)
        return

    try:
        chk = subprocess.run(  # nosec B603
            [sys.executable, "-c", "import quantmetrics_analytics"],
            capture_output=True,
            text=True,
            timeout=30,
            encoding="utf-8",
            errors="replace",
            shell=False,
        )
    except Exception as exc:
        logger.warning("QuantAnalytics import check failed: %s", exc)
        return
    if chk.returncode != 0:
        logger.warning(
            "QuantAnalytics post-run skipped: same Python cannot import quantmetrics_analytics "
            "(install in this env: pip install -e /path/to/quantanalyticsv1). stderr=%s",
            (chk.stderr or "").strip()[:500],
        )
        return

    cmd = [
        sys.executable,
        "-m",
        "quantmetrics_analytics.cli.run_analysis",
        "--dir",
        str(base),
        "--run-id",
        str(ql_emitter.run_id),
        "--reports",
        "all",
    ]
    env = os.environ.copy()
    if not env.get("QUANTMETRICS_ANALYTICS_OUTPUT_DIR", "").strip():
        out_dir = discover_quantanalytics_output_rapport()
        if out_dir is not None:
            env["QUANTMETRICS_ANALYTICS_OUTPUT_DIR"] = str(out_dir)
            logger.debug("QuantAnalytics reports directory: %s", out_dir)
    try:
        proc = subprocess.run(  # nosec B603
            cmd,
            env=env,
            capture_output=True,
            text=True,
            timeout=600,
            encoding="utf-8",
            errors="replace",
            shell=False,
        )
    except FileNotFoundError:
        logger.warning("QuantAnalytics post-run skipped: Python executable not found.")
        return
    except subprocess.TimeoutExpired:
        logger.warning("QuantAnalytics post-run timed out after 600s.")
        return
    except Exception as exc:
        logger.warning("QuantAnalytics post-run failed: %s", exc)
        return

    if proc.returncode != 0:
        err = (proc.stderr or "").strip()
        out = (proc.stdout or "").strip()
        logger.warning(
            "QuantAnalytics exited with %s. stderr=%s stdout=%s",
            proc.returncode,
            err[:2000],
            out[:500],
        )
        return

    err_lines = [ln.strip() for ln in (proc.stderr or "").splitlines() if ln.strip()]
    if err_lines:
        for ln in err_lines[-4:]:
            logger.info("QuantAnalytics: %s", ln)
    else:
        logger.info("QuantAnalytics post-run finished OK (no stderr lines).")
