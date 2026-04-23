"""Optional post-run: copy QuantLog + config snapshot into quantmetrics_os/runs/."""

from __future__ import annotations

import logging
import os
import subprocess  # nosec B404
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.quantbuild.execution.quantlog_emitter import QuantLogEmitter
from src.quantbuild.integration.quantanalytics_post_run import discover_quantanalytics_output_rapport
from src.quantbuild.quantlog_repo import quantbuild_project_root

logger = logging.getLogger(__name__)


def discover_quantmetrics_os_root(quantbuild_root: Path | None = None) -> Path | None:
    """Sibling ``../quantmetrics_os`` next to QuantBuild (same parent only)."""
    root = (quantbuild_root or quantbuild_project_root()).resolve()
    parent = root.parent
    if parent == root:
        return None
    qm = parent / "quantmetrics_os"
    marker = qm / "scripts" / "collect_run_artifact.py"
    if marker.is_file():
        return qm.resolve()
    return None


def _auto_experiment_id(run_id: str) -> str:
    d = datetime.now(timezone.utc).strftime("%Y%m%d")
    tail = run_id.split("_")[-1][:8] if "_" in run_id else run_id[-8:]
    return f"EXP-{d}-{tail}"


def invoke_collect_run_artifacts(cfg: dict[str, Any], ql_emitter: QuantLogEmitter | None) -> None:
    """Run ``quantmetrics_os/scripts/collect_run_artifact.py`` when ``artifacts.enabled`` is true."""
    if ql_emitter is None:
        return
    art = cfg.get("artifacts") or {}
    if not bool(art.get("enabled")):
        return
    if os.environ.get("QUANTMETRICS_ARTIFACTS", "").strip().lower() in {"0", "false", "no", "off"}:
        logger.info("QuantOS artifact collect skipped (QUANTMETRICS_ARTIFACTS disabled).")
        return

    qb_root = quantbuild_project_root()
    qm_root_raw = art.get("quantmetrics_os_root")
    if qm_root_raw:
        qm_root = Path(str(qm_root_raw)).expanduser().resolve()
    else:
        env_qm = os.environ.get("QUANTMETRICS_OS_ROOT", "").strip()
        qm_root = Path(env_qm).expanduser().resolve() if env_qm else discover_quantmetrics_os_root(qb_root)
    if qm_root is None or not qm_root.is_dir():
        logger.warning("QuantOS artifact collect skipped: quantmetrics_os root not found.")
        return

    script = qm_root / "scripts" / "collect_run_artifact.py"
    if not script.is_file():
        logger.warning("QuantOS artifact collect skipped: missing %s", script)
        return

    experiment_id = str(art.get("experiment_id") or "").strip() or _auto_experiment_id(str(ql_emitter.run_id))
    role = str(art.get("role") or "single").strip().lower()
    if role not in {"baseline", "variant", "single"}:
        role = "single"

    cfg_path = cfg.get("_quantbuild_config_path")
    config_yaml = Path(str(cfg_path)).resolve() if cfg_path else None

    bundle = bool(art.get("bundle_analytics", True))
    recent_sec = int(art.get("analytics_recent_seconds", 900))
    analytics_out = None
    if bundle:
        analytics_out = discover_quantanalytics_output_rapport(qb_root)

    cmd: list[str] = [
        sys.executable,
        str(script),
        "--experiment-id",
        experiment_id,
        "--role",
        role,
        "--run-id",
        str(ql_emitter.run_id),
        "--quantbuild-root",
        str(qb_root.resolve()),
        "--quantmetrics-os-root",
        str(qm_root),
        "--analytics-recent-seconds",
        str(recent_sec),
    ]
    if config_yaml is not None and config_yaml.is_file():
        cmd.extend(["--config-yaml", str(config_yaml)])
    if bundle and analytics_out is not None:
        cmd.append("--bundle-analytics")
        cmd.extend(["--analytics-output-dir", str(analytics_out)])

    try:
        proc = subprocess.run(  # nosec B603
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
            encoding="utf-8",
            errors="replace",
            shell=False,
        )
    except Exception as exc:
        logger.warning("QuantOS artifact collect failed: %s", exc)
        return

    if proc.returncode != 0:
        err = (proc.stderr or "").strip()
        logger.warning(
            "QuantOS artifact collect exited %s: stderr=%s stdout=%s",
            proc.returncode,
            err[:1500],
            (proc.stdout or "").strip()[:500],
        )
        return

    out = (proc.stdout or "").strip().splitlines()
    dest = out[-1].strip() if out else ""
    logger.info("QuantOS artifacts collected under: %s", dest)
