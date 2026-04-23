from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def run_step(name: str, command: list[str]) -> dict:
    started = time.time()
    result = subprocess.run(
        command,
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    duration_ms = int((time.time() - started) * 1000)
    return {
        "name": name,
        "command": " ".join(command),
        "exit_code": int(result.returncode),
        "duration_ms": duration_ms,
        "stdout": (result.stdout or "").strip(),
        "stderr": (result.stderr or "").strip(),
        "ok": result.returncode == 0,
    }


def default_steps(python: str) -> list[tuple[str, list[str]]]:
    return [
        (
            "smoke_mock",
            [python, "scripts/ctrader_smoke.py", "--config", "configs/ctrader_icmarkets_demo.yaml", "--mode", "mock"],
        ),
        (
            "recovery_mock",
            [
                python,
                "scripts/recover_execution_state.py",
                "--config",
                "configs/ctrader_icmarkets_demo.yaml",
                "--mode",
                "mock",
                "--strategy",
                "OCLW",
            ],
        ),
        (
            "runtime_once_mock",
            [
                python,
                "scripts/run_runtime_control.py",
                "--config",
                "configs/ctrader_icmarkets_demo.yaml",
                "--mode",
                "mock",
                "--max-iterations",
                "1",
                "--account-status",
                "demo",
            ],
        ),
        (
            "order_lifecycle_mock",
            [
                python,
                "scripts/run_order_lifecycle_check.py",
                "--config",
                "configs/ctrader_icmarkets_demo.yaml",
                "--mode",
                "mock",
                "--direction",
                "BUY",
                "--sl",
                "2495",
                "--tp",
                "2510",
                "--close-after",
                "--account-status",
                "demo",
            ],
        ),
        (
            "orchestration_selector",
            [
                python,
                "scripts/run_account_orchestration_check.py",
                "--config",
                "configs/accounts_baseline.yaml",
                "--instrument",
                "XAUUSD",
            ],
        ),
        (
            "multi_account_single",
            [
                python,
                "scripts/run_multi_account_execution_check.py",
                "--config",
                "configs/accounts_baseline.yaml",
                "--instrument",
                "XAUUSD",
                "--routing-mode",
                "single",
                "--units",
                "100",
            ],
        ),
        (
            "multi_account_primary_backup",
            [
                python,
                "scripts/run_multi_account_execution_check.py",
                "--config",
                "configs/accounts_baseline.yaml",
                "--instrument",
                "XAUUSD",
                "--routing-mode",
                "primary_backup",
                "--units",
                "100",
            ],
        ),
        (
            "multi_account_fanout",
            [
                python,
                "scripts/run_multi_account_execution_check.py",
                "--config",
                "configs/accounts_baseline.yaml",
                "--instrument",
                "XAUUSD",
                "--routing-mode",
                "fanout",
                "--max-fanout-accounts",
                "2",
                "--units",
                "100",
            ],
        ),
    ]


def load_steps_from_profile(profile_name: str, python: str) -> list[tuple[str, list[str]]]:
    profile_path = ROOT / "configs" / "suite_profiles.yaml"
    if not profile_path.exists():
        raise FileNotFoundError(f"suite profile file missing: {profile_path}")
    config = yaml.safe_load(profile_path.read_text(encoding="utf-8")) or {}
    profiles = config.get("profiles", {}) or {}
    profile = profiles.get(profile_name)
    if not profile:
        raise ValueError(f"unknown suite profile: {profile_name}")

    out: list[tuple[str, list[str]]] = []
    for raw_step in profile:
        name = str(raw_step.get("name", "")).strip()
        cmd = [str(python if token == "{python}" else token) for token in (raw_step.get("command", []) or [])]
        if not name or not cmd:
            continue
        out.append((name, cmd))
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Run QuantBridge regression suites.")
    parser.add_argument("--profile", default="", help="Suite profile name from configs/suite_profiles.yaml")
    parser.add_argument("--report-file", default="", help="Optional JSON file to persist suite report")
    args = parser.parse_args()

    python = sys.executable
    if args.profile:
        steps = load_steps_from_profile(profile_name=args.profile, python=python)
    else:
        steps = default_steps(python)

    results = [run_step(name=name, command=cmd) for name, cmd in steps]
    failed = [r for r in results if not r["ok"]]
    output = {
        "suite": args.profile or "quantbridge_regression_mock",
        "total_steps": len(results),
        "passed": len(results) - len(failed),
        "failed": len(failed),
        "ok": len(failed) == 0,
        "results": results,
    }
    if args.report_file:
        report_path = Path(args.report_file)
        if not report_path.is_absolute():
            report_path = ROOT / report_path
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(output, indent=2))
    return 0 if len(failed) == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
