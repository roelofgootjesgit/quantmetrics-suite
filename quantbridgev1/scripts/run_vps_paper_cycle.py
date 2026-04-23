from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _run(command: list[str]) -> dict:
    started = time.time()
    proc = subprocess.run(command, cwd=str(ROOT), capture_output=True, text=True)
    return {
        "command": " ".join(command),
        "exit_code": int(proc.returncode),
        "duration_ms": int((time.time() - started) * 1000),
        "stdout": (proc.stdout or "").strip(),
        "stderr": (proc.stderr or "").strip(),
        "ok": proc.returncode == 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one VPS paper orchestration cycle.")
    parser.add_argument("--profile", default="vps_paper")
    parser.add_argument("--report-file", default="logs/vps_paper_cycle_report.json")
    args = parser.parse_args()

    python = sys.executable
    suite_report = ROOT / args.report_file
    cmd = [
        python,
        "scripts/run_regression_suite.py",
        "--profile",
        args.profile,
        "--report-file",
        str(suite_report),
    ]
    result = _run(cmd)
    output = {
        "cycle": "vps_paper",
        "profile": args.profile,
        "ok": bool(result["ok"]),
        "suite_report_file": str(suite_report),
        "runner": result,
    }
    print(json.dumps(output, indent=2))
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
