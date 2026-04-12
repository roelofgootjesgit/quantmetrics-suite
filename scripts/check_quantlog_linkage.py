#!/usr/bin/env python3
"""Verify QuantBuild ↔ QuantLog integration.

1. If QuantLog repo is found: run ``quantlog.cli validate-events`` on the minimal fixture.
2. Compare ``NO_ACTION`` reason sets between QuantLog schema and QuantBuild ``quantlog_no_action``.

Exit codes:
  0 — OK, or QuantLog repo missing in *non-strict* mode (warning printed to stderr).
  1 — Validation/schema mismatch, or repo missing in ``--strict`` / ``QUANTLOG_LINKAGE_STRICT=1``.

Environment:
  QUANTLOG_REPO_PATH / QUANTLOG_ROOT — explicit QuantLog root
  QUANTLOG_LINKAGE_STRICT — if ``1``/``true``, treat missing repo as failure
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def _strict_default() -> bool:
    v = os.environ.get("QUANTLOG_LINKAGE_STRICT", "").strip().lower()
    return v in ("1", "true", "yes")


def _run_validate_events(
    *,
    repo: Path,
    path: Path,
    python: str,
) -> tuple[int, dict]:
    src = repo / "src"
    env = os.environ.copy()
    pfx = str(src.resolve())
    env["PYTHONPATH"] = pfx if not env.get("PYTHONPATH") else f"{pfx}{os.pathsep}{env['PYTHONPATH']}"
    proc = subprocess.run(
        [python, "-m", "quantlog.cli", "validate-events", "--path", str(path)],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    try:
        data = json.loads(proc.stdout.strip() or "{}")
    except json.JSONDecodeError:
        data = {"parse_error": True, "stdout": proc.stdout, "stderr": proc.stderr}
    return proc.returncode, data


def _run_no_action_alignment(*, repo: Path, quantbuild_src: Path, python: str) -> tuple[bool, str]:
    env = os.environ.copy()
    combined = f"{repo / 'src'}{os.pathsep}{quantbuild_src}"
    env["PYTHONPATH"] = combined if not env.get("PYTHONPATH") else f"{combined}{os.pathsep}{env['PYTHONPATH']}"
    code = (
        "from quantlog.events.schema import NO_ACTION_REASONS_ALLOWED\n"
        "from quantbuild.execution.quantlog_no_action import _CANONICAL_NO_ACTION\n"
        "ql, qb = NO_ACTION_REASONS_ALLOWED, _CANONICAL_NO_ACTION\n"
        "mi, ej = ql - qb, qb - ql\n"
        "if mi or ej:\n"
        "    print('QuantLog NO_ACTION set differs from QuantBuild _CANONICAL_NO_ACTION')\n"
        "    if mi:\n"
        "        print('  in QuantLog only:', sorted(mi))\n"
        "    if ej:\n"
        "        print('  in QuantBuild only:', sorted(ej))\n"
        "    raise SystemExit(1)\n"
        "print('NO_ACTION reason sets match (%d codes)' % len(ql))\n"
    )
    proc = subprocess.run(
        [python, "-c", code],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    out = (proc.stdout + proc.stderr).strip()
    return proc.returncode == 0, out


def main() -> int:
    parser = argparse.ArgumentParser(description="Check QuantBuild/QuantLog linkage")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Fail if QuantLog repo is missing (else env QUANTLOG_LINKAGE_STRICT=1)",
    )
    args = parser.parse_args()
    strict = args.strict or _strict_default()

    fixture = _REPO_ROOT / "tests" / "fixtures" / "quantlog" / "minimal_day"
    quantbuild_src = _REPO_ROOT / "src"

    if not fixture.is_dir():
        print(f"ERROR: fixture missing: {fixture}", file=sys.stderr)
        return 1

    from src.quantbuild.quantlog_repo import resolve_quantlog_repo_path

    repo = resolve_quantlog_repo_path()
    python = sys.executable

    if repo is None:
        msg = (
            "QuantLog linkage: repository not found (set QUANTLOG_REPO_PATH or clone as "
            "sibling 'quantlogv1' /opt/quantbuild/quantlogv1). "
            "validate-events and NO_ACTION alignment were skipped."
        )
        print(f"WARNING: {msg}", file=sys.stderr)
        return 1 if strict else 0

    print(f"QuantLog repo: {repo}")
    print(f"Fixture: {fixture}")

    rc, report = _run_validate_events(repo=repo, path=fixture, python=python)
    errors = report.get("errors_total")
    if report.get("parse_error"):
        print("ERROR: quantlog.cli did not return JSON", file=sys.stderr)
        print(report.get("stdout", ""), file=sys.stderr)
        print(report.get("stderr", ""), file=sys.stderr)
        return 1
    print(f"validate-events: returncode={rc} errors_total={errors}")
    if errors is not None and int(errors) > 0:
        print(json.dumps(report, indent=2, ensure_ascii=True))
        return 1
    if rc != 0 and (errors is None or int(errors) == 0):
        print(f"ERROR: validate-events exited {rc} (stderr below)", file=sys.stderr)
        print(report.get("stderr", ""), file=sys.stderr)
        return 1

    ok, align_msg = _run_no_action_alignment(repo=repo, quantbuild_src=quantbuild_src, python=python)
    print(align_msg)
    if not ok:
        return 1

    print("QuantLog linkage OK.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
