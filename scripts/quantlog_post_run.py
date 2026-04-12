"""Post-run QuantLog pipeline for QuantBuild event output.

Runs:
  1) validate-events
  2) summarize-day
  3) score-run
  4) replay-trace (first available trace)
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from src.quantbuild.config import load_config
from src.quantbuild.quantlog_repo import resolve_quantlog_repo_path


def _default_quantlog_repo_path() -> Path:
    """Resolved QuantLog root, or a fallback path for argparse when not found."""
    found = resolve_quantlog_repo_path()
    if found is not None:
        return found
    env = os.environ.get("QUANTLOG_REPO_PATH", "").strip()
    if env:
        return Path(env)
    return Path("/opt/quantbuild/quantlogv1")


def _run_json(cmd: list[str], *, env: dict[str, str] | None = None) -> dict:
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True, env=env)
    if proc.returncode not in (0, 2, 3, 4):
        raise RuntimeError(f"command failed ({proc.returncode}): {' '.join(cmd)}\n{proc.stderr}")
    try:
        return json.loads(proc.stdout.strip() or "{}")
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"invalid JSON output from {' '.join(cmd)}: {exc}") from exc


def _first_trace_id(day_path: Path) -> str | None:
    qb_file = day_path / "quantbuild.jsonl"
    if not qb_file.exists():
        return None
    for line in qb_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except Exception:
            continue
        trace_id = obj.get("trace_id")
        if isinstance(trace_id, str) and trace_id.strip():
            return trace_id
    return None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run QuantLog post-run checks for QuantBuild")
    parser.add_argument("--config", required=True, help="QuantBuild config path")
    parser.add_argument(
        "--quantlog-repo-path",
        default=str(_default_quantlog_repo_path()),
        help="Path to QuantLog repository (or set QUANTLOG_REPO_PATH)",
    )
    parser.add_argument(
        "--date",
        default=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        help="UTC date folder in quantlog base path",
    )
    parser.add_argument("--pass-threshold", type=int, default=95)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    cfg = load_config(args.config)

    ql_cfg = cfg.get("quantlog", {}) or {}
    if not bool(ql_cfg.get("enabled", False)):
        print(
            "QuantLog is disabled in the resolved config (quantlog.enabled is false or missing).\n"
            "Nothing to validate. Note: configs/default.yaml sets quantlog.enabled: false; if your "
            "YAML only sets base_path and omits enabled, the merge keeps enabled=false.\n"
            "Fix: add under quantlog: `enabled: true` (and matching base_path), or git pull — "
            "demo_strict_prod_v2.yaml / strict_prod_v2.yaml in repo already set enabled: true."
        )
        return 2

    events_base = Path(str(ql_cfg.get("base_path", "data/quantlog_events")))
    day_path = events_base / args.date
    if not day_path.exists():
        raise RuntimeError(f"QuantLog day path does not exist: {day_path}")

    quantlog_repo = Path(args.quantlog_repo_path)
    if not quantlog_repo.exists() or not (quantlog_repo / "src" / "quantlog").is_dir():
        raise RuntimeError(
            f"QuantLog repo path invalid or missing (no src/quantlog): {quantlog_repo}. "
            "Clone QuantLog, set QUANTLOG_REPO_PATH, or run: python scripts/check_quantlog_linkage.py"
        )
    quantlog_src = quantlog_repo / "src"
    if not quantlog_src.exists():
        raise RuntimeError(f"QuantLog src path does not exist: {quantlog_src}")
    run_env = os.environ.copy()
    run_env["PYTHONPATH"] = (
        str(quantlog_src)
        if not run_env.get("PYTHONPATH")
        else f"{quantlog_src}{os.pathsep}{run_env.get('PYTHONPATH')}"
    )
    python = sys.executable

    validate = _run_json(
        [python, "-m", "quantlog.cli", "validate-events", "--path", str(day_path)],
        env=run_env,
    )
    summarize = _run_json(
        [python, "-m", "quantlog.cli", "summarize-day", "--path", str(day_path)],
        env=run_env,
    )
    score = _run_json(
        [
            python,
            "-m",
            "quantlog.cli",
            "score-run",
            "--path",
            str(day_path),
            "--pass-threshold",
            str(args.pass_threshold),
        ]
        ,
        env=run_env,
    )
    trace_id = _first_trace_id(day_path)
    replay = {}
    if trace_id:
        replay = _run_json(
            [
                python,
                "-m",
                "quantlog.cli",
                "replay-trace",
                "--path",
                str(day_path),
                "--trace-id",
                trace_id,
            ]
            ,
            env=run_env,
        )

    print("QUANTLOG POST-RUN REPORT")
    print(f"day_path={day_path}")
    print(f"validate_errors={validate.get('errors_total', 'n/a')}")
    print(f"events_total={summarize.get('events_total', 'n/a')}")
    print(
        f"quality_score={score.get('score', 'n/a')} passed={score.get('passed', False)} "
        f"threshold={score.get('pass_threshold', args.pass_threshold)}"
    )
    if replay:
        print(f"replay_trace_id={trace_id} events_found={replay.get('events_found', 0)}")

    errors_total = int(validate.get("errors_total", 0))
    score_passed = bool(score.get("passed", False))
    replay_ok = (not replay) or int(replay.get("events_found", 0)) > 0
    if errors_total == 0 and score_passed and replay_ok:
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

