#!/usr/bin/env python3
"""P0-E gate: run QuantBuild automated tests before analytics rerun on fresh JSONL.

Usage (from quantbuildv1 repo root)::

    python scripts/p0_stack_validate.py

Exit code is pytest's exit code (0 = all checks passed).
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "tests/",
        "-q",
        "--tb=short",
        "--ignore=tests/test_finnhub_source.py",
    ]
    print("Running:", " ".join(cmd), f"(cwd={root})")
    proc = subprocess.run(cmd, cwd=str(root))
    print("pytest exit:", proc.returncode)
    if proc.returncode == 0:
        print(
            "Next (manual P0-E): run one full backtest or trading day, write QuantLog JSONL, "
            "then run the same QuantAnalytics pipeline and confirm checklist in docs/P0_FIX_PLAN.md."
        )
    return int(proc.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
