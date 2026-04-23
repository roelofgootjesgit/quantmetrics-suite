#!/usr/bin/env python3
"""SPRINT 5 — compact validation gate (pytest smoke + payload unit tests).

Run from quantbuildv1 root::

    python scripts/p0_sprint5_smoke.py
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    tests = [
        "tests/test_signal_evaluated_payload.py",
        "tests/test_quantlog_jsonl_contract.py",
        "tests/test_backtest.py::TestBacktestQuantLog::test_writes_events_when_quantlog_enabled",
    ]
    cmd = [sys.executable, "-m", "pytest", "-q", "--tb=short", *tests]
    print("Running:", " ".join(cmd), flush=True)
    proc = subprocess.run(cmd, cwd=str(root))
    return int(proc.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
