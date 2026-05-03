"""Copy backtest + QuantAnalytics outputs into ``quantresearch/runs/<experiment_id>/`` for team review."""

from __future__ import annotations

import json
import logging
import os
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from src.quantbuild.execution.quantlog_emitter import QuantLogEmitter
from src.quantbuild.integration.quantanalytics_post_run import discover_quantanalytics_output_rapport
from src.quantbuild.quantlog_repo import quantbuild_project_root

logger = logging.getLogger(__name__)


def _sanitize_segment(name: str) -> str:
    s = "".join(c if c.isalnum() or c in "-_" else "_" for c in name.strip())
    return s or "unnamed"


def resolve_quantresearch_root() -> Optional[Path]:
    """``QUANTRESEARCH_ROOT``, or ``<QUANTMETRICS_SUITE_ROOT>/quantresearch``, or sibling of quantbuild."""
    env = os.environ.get("QUANTRESEARCH_ROOT", "").strip()
    if env:
        p = Path(env).expanduser().resolve()
        return p if p.is_dir() else None
    suite = os.environ.get("QUANTMETRICS_SUITE_ROOT", "").strip()
    if suite:
        p = (Path(suite) / "quantresearch").resolve()
        if p.is_dir():
            return p
    qb = quantbuild_project_root()
    sib = (qb.parent / "quantresearch").resolve()
    if sib.is_dir():
        return sib
    return None


def invoke_quantresearch_run_bundle(
    cfg: dict[str, Any],
    ql_emitter: QuantLogEmitter | None,
    metrics: Optional[Dict[str, Any]] = None,
) -> Optional[Path]:
    """If ``quantresearch_runs.enabled``, copy JSONL (if present), latest analytics, metrics, manifest."""
    if ql_emitter is None:
        return None
    qrr = cfg.get("quantresearch_runs") or {}
    if not bool(qrr.get("enabled", False)):
        return None

    qroot = resolve_quantresearch_root()
    if qroot is None:
        logger.warning("quantresearch_runs: quantresearch directory not found (set QUANTRESEARCH_ROOT or QUANTMETRICS_SUITE_ROOT).")
        return None

    experiment_id = str(qrr.get("experiment_id") or "").strip()
    if not experiment_id:
        tail = str(ql_emitter.run_id).split("_")[-1][:8] if "_" in str(ql_emitter.run_id) else str(ql_emitter.run_id)[-8:]
        experiment_id = f"EXP-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{tail}"

    dest = (qroot / "runs" / _sanitize_segment(experiment_id)).resolve()
    dest.mkdir(parents=True, exist_ok=True)

    qb_root = quantbuild_project_root()
    jsonl_src = qb_root / "data" / "quantlog_events" / "runs" / f"{ql_emitter.run_id}.jsonl"
    if jsonl_src.is_file():
        shutil.copy2(jsonl_src, dest / "quantlog_events.jsonl")
    else:
        logger.info(
            "quantresearch_runs: no consolidated JSONL at %s (set quantlog.consolidated_run_file: true for one-file export)",
            jsonl_src,
        )

    analytics_out = discover_quantanalytics_output_rapport(qb_root)
    analytics_copied = 0
    adir = dest / "analytics"
    if analytics_out is not None and analytics_out.is_dir():
        adir.mkdir(parents=True, exist_ok=True)
        cutoff = time.time() - max(120, int(qrr.get("analytics_recent_seconds", 900)))
        rid = str(ql_emitter.run_id)
        for p in sorted(analytics_out.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True):
            if not p.is_file() or p.stat().st_mtime < cutoff:
                continue
            if p.suffix.lower() not in {".txt", ".md", ".json"}:
                continue
            try:
                txt = p.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if rid in txt or analytics_copied < 6:
                shutil.copy2(p, adir / p.name)
                analytics_copied += 1
            if analytics_copied >= 24:
                break

    manifest: Dict[str, Any] = {
        "run_id": str(ql_emitter.run_id),
        "experiment_id": experiment_id,
        "bundled_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "quantbuild_root": str(qb_root.resolve()),
        "quantresearch_root": str(qroot.resolve()),
        "bundle_dest": str(dest),
        "quantlog_consolidated": str(jsonl_src.resolve()) if jsonl_src.is_file() else None,
        "analytics_files_copied": analytics_copied,
        "_quantbuild_config_path": cfg.get("_quantbuild_config_path"),
        "ny_sweep_reversion_config": (cfg.get("backtest") or {}).get("ny_sweep_reversion_config"),
    }
    (dest / "run_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    if metrics is not None:
        (dest / "backtest_metrics.json").write_text(
            json.dumps(metrics, indent=2, default=str) + "\n",
            encoding="utf-8",
        )

    logger.info("quantresearch_runs: bundle written to %s", dest)
    return dest
