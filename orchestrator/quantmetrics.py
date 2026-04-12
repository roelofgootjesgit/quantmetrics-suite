#!/usr/bin/env python3
"""QuantMetrics OS — thin orchestrator for QuantBuild / QuantBridge.

Loads `orchestrator/.env` into the process environment (non-destructive: existing
OS vars win). Put all secrets and QUANTBUILD_ROOT / QUANTBRIDGE_ROOT here on the VPS.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

_ORCHESTRATOR_DIR = Path(__file__).resolve().parent


def _bootstrap_env() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    env_path = _ORCHESTRATOR_DIR / ".env"
    if env_path.is_file():
        # Orchestrator .env is the intended VPS source of truth when using quantmetrics_os.
        load_dotenv(env_path, override=True)


def _require_dir(var: str) -> Path:
    raw = os.environ.get(var, "").strip()
    if not raw:
        print(f"Missing environment variable: {var}", file=sys.stderr)
        sys.exit(2)
    p = Path(raw).expanduser().resolve()
    if not p.is_dir():
        print(f"{var} is not a directory: {p}", file=sys.stderr)
        sys.exit(2)
    return p


def _quantbuild_python(qb_root: Path) -> str:
    explicit = os.environ.get("PYTHON", "").strip()
    if explicit and Path(explicit).is_file():
        return explicit
    for candidate in (
        qb_root / ".venv" / "bin" / "python",
        qb_root / ".venv" / "Scripts" / "python.exe",
    ):
        if candidate.is_file():
            return str(candidate)
    return sys.executable


def cmd_build(args: argparse.Namespace) -> int:
    root = _require_dir("QUANTBUILD_ROOT")
    python = _quantbuild_python(root)
    config = args.config.strip()
    cmd = [python, "-m", "src.quantbuild.app", "--config", config, "live"]
    if args.dry_run:
        cmd.append("--dry-run")
    if args.real:
        cmd.append("--real")
    env = os.environ.copy()
    extra = str(root)
    env["PYTHONPATH"] = f"{extra}{os.pathsep}{env['PYTHONPATH']}" if env.get("PYTHONPATH") else extra
    print(f"+ {' '.join(cmd)}")
    print(f"(cwd) {root}")
    return int(subprocess.call(cmd, cwd=str(root), env=env))


def cmd_bridge_regression(args: argparse.Namespace) -> int:
    bridge_root = _require_dir("QUANTBRIDGE_ROOT")
    qb_root = _require_dir("QUANTBUILD_ROOT")
    python = _quantbuild_python(qb_root)
    cmd = [python, "scripts/run_regression_suite.py"]
    if args.profile:
        cmd.extend(["--profile", args.profile])
    if args.report_file:
        cmd.extend(["--report-file", args.report_file])
    print(f"+ {' '.join(cmd)}")
    print(f"(cwd) {bridge_root}")
    return int(subprocess.call(cmd, cwd=str(bridge_root), env=os.environ.copy()))


def main() -> int:
    _bootstrap_env()
    parser = argparse.ArgumentParser(prog="quantmetrics.py", description="QuantBuild / QuantBridge orchestrator")
    sub = parser.add_subparsers(dest="command", required=True)

    p_build = sub.add_parser("build", help="Run QuantBuild live (env inherited by child)")
    p_build.add_argument("-c", "--config", required=True, help="YAML path relative to QUANTBUILD_ROOT")
    p_build.add_argument("--dry-run", action="store_true", help="Append --dry-run to quantbuild app")
    p_build.add_argument("--real", action="store_true", help="Append --real for live orders")
    p_build.set_defaults(func=cmd_build)

    p_bridge = sub.add_parser("bridge", help="QuantBridge helpers")
    bsub = p_bridge.add_subparsers(dest="bridge_cmd", required=True)

    p_reg = bsub.add_parser(
        "regression",
        help="Run scripts/run_regression_suite.py (mock suite; config paths are inside the script)",
    )
    p_reg.add_argument("--profile", default="", help="Optional suite profile from configs/suite_profiles.yaml")
    p_reg.add_argument("--report-file", default="", help="Optional JSON report path (under bridge root if relative)")
    p_reg.set_defaults(func=cmd_bridge_regression)

    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
