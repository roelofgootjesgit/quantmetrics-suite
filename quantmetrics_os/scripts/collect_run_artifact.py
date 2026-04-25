#!/usr/bin/env python3
"""Bundle backtest artifacts into quantmetrics_os/runs/<experiment>/<role>/.

Writes ``config_snapshot.yaml`` (copy of ``--config`` entry YAML) and optionally
``resolved_config.yaml`` (merged effective config from ``--resolved-config-yaml``).

Invoked by QuantBuild after a run (optional) or manually:

    python scripts/collect_run_artifact.py \\
      --experiment-id EXP-20250423-test \\
      --run-id qb_run_... \\
      --quantbuild-root ../quantbuild \\
      --config-yaml ../quantbuild/configs/backtest_2025_full_strict_prod.yaml
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


def _sanitize_segment(name: str) -> str:
    s = "".join(c if c.isalnum() or c in "-_" else "_" for c in name.strip())
    return s or "unnamed"


def discover_quantmetrics_os_root(explicit: Path | None) -> Path:
    if explicit is not None:
        return explicit.resolve()
    env = os.environ.get("QUANTMETRICS_OS_ROOT", "").strip()
    if env:
        return Path(env).expanduser().resolve()
    here = Path(__file__).resolve().parent.parent
    return here


def collect(
    *,
    experiment_id: str,
    role: str,
    run_id: str,
    quantbuild_root: Path,
    quantmetrics_os_root: Path,
    config_yaml: Path | None,
    resolved_config_yaml: Path | None,
    bundle_analytics: bool,
    analytics_output_dir: Path | None,
    analytics_recent_seconds: int,
) -> Path:
    role_norm = _sanitize_segment(role)
    if not role_norm:
        raise ValueError(f"role must be a non-empty string, got {role!r}")

    runs = quantmetrics_os_root / "runs"
    dest = runs / _sanitize_segment(experiment_id) / role_norm
    dest.mkdir(parents=True, exist_ok=True)

    jsonl_src = quantbuild_root / "data" / "quantlog_events" / "runs" / f"{run_id}.jsonl"
    if not jsonl_src.is_file():
        raise FileNotFoundError(f"QuantLog consolidated run not found: {jsonl_src}")

    shutil.copy2(jsonl_src, dest / "quantlog_events.jsonl")

    config_dest_rel = ""
    if config_yaml is not None and config_yaml.is_file():
        shutil.copy2(config_yaml, dest / "config_snapshot.yaml")
        config_dest_rel = "config_snapshot.yaml"

    resolved_dest_rel = ""
    if resolved_config_yaml is not None and resolved_config_yaml.is_file():
        shutil.copy2(resolved_config_yaml, dest / "resolved_config.yaml")
        resolved_dest_rel = "resolved_config.yaml"

    analytics_copied = 0
    analytics_dir = dest / "analytics"
    if bundle_analytics and analytics_output_dir is not None and analytics_output_dir.is_dir():
        analytics_dir.mkdir(parents=True, exist_ok=True)
        cutoff = time.time() - max(60, analytics_recent_seconds)
        for p in sorted(analytics_output_dir.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True):
            if not p.is_file():
                continue
            if p.stat().st_mtime < cutoff:
                continue
            if p.suffix.lower() not in {".txt", ".md", ".json"}:
                continue
            shutil.copy2(p, analytics_dir / p.name)
            analytics_copied += 1
            if analytics_copied >= 40:
                break

    run_info: dict = {
        "run_id": run_id,
        "experiment_id": experiment_id,
        "role": role_norm,
        "collected_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "quantbuild_root": str(quantbuild_root.resolve()),
        "quantlog_source": str(jsonl_src.resolve()),
        "config_snapshot": config_dest_rel,
        "config_source_path": str(config_yaml.resolve()) if config_yaml else None,
        "resolved_config": resolved_dest_rel,
        "resolved_config_source_path": str(resolved_config_yaml.resolve())
        if resolved_config_yaml
        else None,
    }
    if bundle_analytics:
        run_info["analytics_files_copied"] = analytics_copied
    (dest / "run_info.json").write_text(json.dumps(run_info, indent=2) + "\n", encoding="utf-8")

    return dest


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect run artifacts under quantmetrics_os/runs/")
    parser.add_argument("--experiment-id", required=True)
    parser.add_argument(
        "--role",
        default="single",
        help="Run role folder name under runs/<experiment-id>/ (will be sanitized).",
    )
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--quantbuild-root", type=Path, default=None)
    parser.add_argument("--quantmetrics-os-root", type=Path, default=None)
    parser.add_argument("--config-yaml", type=Path, default=None)
    parser.add_argument(
        "--resolved-config-yaml",
        type=Path,
        default=None,
        help="Merged effective config (default+extends+env), redacted; stored as resolved_config.yaml",
    )
    parser.add_argument(
        "--bundle-analytics",
        action="store_true",
        help="Copy recent report files from --analytics-output-dir into analytics/",
    )
    parser.add_argument("--analytics-output-dir", type=Path, default=None)
    parser.add_argument(
        "--analytics-recent-seconds",
        type=int,
        default=900,
        help="Only copy analytics files modified within this many seconds (default 900).",
    )
    args = parser.parse_args()

    qb = args.quantbuild_root
    if qb is None:
        env = os.environ.get("QUANTBUILD_ROOT", "").strip()
        qb = Path(env).expanduser().resolve() if env else None
    if qb is None:
        print("[collect_run_artifact] Need --quantbuild-root or QUANTBUILD_ROOT", file=sys.stderr)
        return 2

    qmos = discover_quantmetrics_os_root(args.quantmetrics_os_root)
    dest = collect(
        experiment_id=args.experiment_id,
        role=args.role,
        run_id=args.run_id,
        quantbuild_root=qb.resolve(),
        quantmetrics_os_root=qmos,
        config_yaml=args.config_yaml,
        resolved_config_yaml=args.resolved_config_yaml,
        bundle_analytics=bool(args.bundle_analytics),
        analytics_output_dir=args.analytics_output_dir,
        analytics_recent_seconds=int(args.analytics_recent_seconds),
    )
    print(str(dest.resolve()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
