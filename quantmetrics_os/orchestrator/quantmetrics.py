#!/usr/bin/env python3
"""QuantOS — thin orchestrator for QuantBuild / QuantBridge / QuantLog / QuantAnalytics.

Loads `orchestrator/.env` into the process environment (non-destructive: existing
OS vars win). Put all secrets and QUANTBUILD_ROOT / QUANTBRIDGE_ROOT here on the VPS.

QuantAnalytics (quantmetrics_analytics): set QUANTANALYTICS_ROOT to the quantanalyticsv1
checkout and install the package into the QuantBuild venv (``pip install -e ...``) or rely
on PYTHONPATH (this script prepends QUANTANALYTICS_ROOT for ``analyze`` / ``backtest --analyze``).
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

_ORCHESTRATOR_DIR = Path(__file__).resolve().parent
_QUANTMETRICS_OS_ROOT = _ORCHESTRATOR_DIR.parent

# Resolve expected consolidated QuantLog JSONL from a QuantBuild YAML (same rules as backtest).
_RESOLVE_QUANTLOG_JSONL = """\
import sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd()))
from src.quantbuild.config import load_config
from src.quantbuild.backtest.engine import _init_backtest_quantlog
cfg = load_config(sys.argv[1])
em = _init_backtest_quantlog(cfg)
if em is None:
    sys.exit(2)
cp = em.consolidated_path
if cp:
    print(cp.resolve(), flush=True)
    sys.exit(0)
sys.exit(3)
"""


def _bootstrap_env() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    env_path = _ORCHESTRATOR_DIR / ".env"
    if env_path.is_file():
        # Orchestrator .env is the intended VPS source of truth when using QuantOS (repo folder quantmetrics_os).
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


def _quantbuild_env(qb_root: Path) -> dict[str, str]:
    env = os.environ.copy()
    extra = str(qb_root.resolve())
    env["PYTHONPATH"] = f"{extra}{os.pathsep}{env['PYTHONPATH']}" if env.get("PYTHONPATH") else extra
    return env


def _analytics_env(qb_root: Path, analytics_root: Path) -> dict[str, str]:
    env = _quantbuild_env(qb_root)
    ar = str(analytics_root.resolve())
    pp = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = f"{ar}{os.pathsep}{pp}" if pp else ar
    return env


def _resolve_quantlog_consolidated_jsonl(qb_root: Path, python_exe: str, config_rel: str) -> Path | None:
    proc = subprocess.run(
        [python_exe, "-c", _RESOLVE_QUANTLOG_JSONL, config_rel.strip()],
        cwd=str(qb_root),
        capture_output=True,
        text=True,
        env=_quantbuild_env(qb_root),
    )
    if proc.returncode != 0:
        return None
    line = (proc.stdout or "").strip().splitlines()
    if not line:
        return None
    p = Path(line[-1].strip()).expanduser().resolve()
    return p if p.is_file() else None


def cmd_build(args: argparse.Namespace) -> int:
    root = _require_dir("QUANTBUILD_ROOT")
    python = _quantbuild_python(root)
    config = args.config.strip()
    env = _quantbuild_env(root)

    if getattr(args, "notify_start", False):
        notify_cmd = [
            python,
            "-m",
            "src.quantbuild.app",
            "--config",
            config,
            "suite-notify",
            "start",
            *args.notify_components.split(),
        ]
        if args.real:
            notify_cmd.append("--real")
        else:
            notify_cmd.append("--dry-run")
        print(f"+ {' '.join(notify_cmd)}")
        rc = int(subprocess.call(notify_cmd, cwd=str(root), env=env))
        if rc != 0:
            return rc

    cmd = [python, "-m", "src.quantbuild.app", "--config", config, "live"]
    if args.dry_run:
        cmd.append("--dry-run")
    if args.real:
        cmd.append("--real")
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


def _run_research_digest(quantmetrics_os_root: Path) -> int:
    """Regenerate research/runs_digest.md + runs_registry.json from runs/."""
    script = quantmetrics_os_root / "scripts" / "research_digest.py"
    if not script.is_file():
        print(f"[quantmetrics] research_digest skipped (missing {script})", file=sys.stderr)
        return 0
    cmd = [sys.executable, str(script)]
    print(f"+ {' '.join(cmd)}")
    print(f"(cwd) {quantmetrics_os_root}")
    return int(subprocess.call(cmd, cwd=str(quantmetrics_os_root), env=os.environ.copy()))


def _run_quantanalytics(
    qb_root: Path,
    analytics_root: Path,
    *,
    argv: list[str],
) -> int:
    python = _quantbuild_python(qb_root)
    cmd = [python, "-m", "quantmetrics_analytics.cli.run_analysis", *argv]
    env = _analytics_env(qb_root, analytics_root)
    print(f"+ {' '.join(cmd)}")
    print(f"(cwd) {analytics_root}")
    return int(subprocess.call(cmd, cwd=str(analytics_root), env=env))


def cmd_analyze(args: argparse.Namespace) -> int:
    qb_root = _require_dir("QUANTBUILD_ROOT")
    analytics_root = _require_dir("QUANTANALYTICS_ROOT")

    inputs = sum(
        1 for k in ("jsonl", "glob_pattern", "dir_path") if getattr(args, k, None) is not None
    )
    if inputs != 1:
        print("Specify exactly one of: --jsonl, --glob, --dir", file=sys.stderr)
        return 2

    tail: list[str] = []
    if getattr(args, "jsonl", None):
        tail.extend(["--jsonl", str(Path(args.jsonl).expanduser().resolve())])
    elif getattr(args, "glob_pattern", None):
        tail.extend(["--glob", args.glob_pattern])
    else:
        tail.extend(["--dir", str(Path(args.dir_path).expanduser().resolve())])

    tail.extend(["--reports", args.reports])
    if getattr(args, "output", None):
        tail.extend(["--output", str(Path(args.output).expanduser().resolve())])
    if getattr(args, "stdout", False):
        tail.append("--stdout")

    return _run_quantanalytics(qb_root, analytics_root, argv=tail)


def cmd_backtest(args: argparse.Namespace) -> int:
    qb_root = _require_dir("QUANTBUILD_ROOT")
    python = _quantbuild_python(qb_root)
    env = _quantbuild_env(qb_root)
    config = args.config.strip()

    cmd = [python, "-m", "src.quantbuild.app", "--config", config, "backtest"]
    if getattr(args, "days", None) is not None:
        cmd.extend(["--days", str(args.days)])
    if getattr(args, "start_date", None):
        cmd.extend(["--start-date", args.start_date])
    if getattr(args, "end_date", None):
        cmd.extend(["--end-date", args.end_date])

    print(f"+ {' '.join(cmd)}")
    print(f"(cwd) {qb_root}")
    rc = int(subprocess.call(cmd, cwd=str(qb_root), env=env))
    if rc != 0:
        return rc

    analyze_rc = 0
    if getattr(args, "analyze", False):
        analytics_root = _require_dir("QUANTANALYTICS_ROOT")

        jsonl_path: Path | None = None
        if getattr(args, "analyze_jsonl", None):
            jsonl_path = Path(args.analyze_jsonl).expanduser().resolve()
            if not jsonl_path.is_file():
                print(f"--analyze-jsonl is not a file: {jsonl_path}", file=sys.stderr)
                analyze_rc = 5
        else:
            resolved = _resolve_quantlog_consolidated_jsonl(qb_root, python, config)
            if resolved is not None and resolved.is_file():
                jsonl_path = resolved

        tail: list[str] = []
        if analyze_rc == 0 and jsonl_path is not None:
            tail.extend(["--jsonl", str(jsonl_path)])
        elif analyze_rc == 0 and getattr(args, "analyze_dir", None):
            tail.extend(["--dir", str(Path(args.analyze_dir).expanduser().resolve())])
        elif analyze_rc == 0:
            print(
                "Analyze skipped: could not find QuantLog JSONL. Options:\n"
                "  • Enable quantlog + consolidated_run_file in the same YAML and re-run, or\n"
                "  • Pass --analyze-jsonl PATH to the JSONL produced by the run, or\n"
                "  • Pass --analyze-dir DIR (all *.jsonl under that tree).",
                file=sys.stderr,
            )
            analyze_rc = 6

        if analyze_rc == 0 and tail:
            tail.extend(["--reports", args.analyze_reports])
            if getattr(args, "analyze_output", None):
                tail.extend(["--output", str(Path(args.analyze_output).expanduser().resolve())])
            if getattr(args, "analyze_stdout", False):
                tail.append("--stdout")
            analyze_rc = _run_quantanalytics(qb_root, analytics_root, argv=tail)

    if not getattr(args, "no_research_digest", False):
        dr = _run_research_digest(_QUANTMETRICS_OS_ROOT)
        if dr != 0:
            return dr

    return analyze_rc


def main() -> int:
    _bootstrap_env()
    parser = argparse.ArgumentParser(
        prog="quantmetrics.py",
        description="QuantBuild / QuantBridge / QuantAnalytics orchestrator",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_build = sub.add_parser("build", help="Run QuantBuild live (env inherited by child)")
    p_build.add_argument("-c", "--config", required=True, help="YAML path relative to QUANTBUILD_ROOT")
    p_build.add_argument("--dry-run", action="store_true", help="Append --dry-run to quantbuild app")
    p_build.add_argument("--real", action="store_true", help="Append --real for live orders")
    p_build.add_argument(
        "--notify-start",
        action="store_true",
        help="Send Telegram suite-notify start (version + run settings) before live",
    )
    p_build.add_argument(
        "--notify-components",
        default="build bridge quantlog",
        help="Words after `suite-notify start` (default: build bridge quantlog)",
    )
    p_build.set_defaults(func=cmd_build)

    p_bt = sub.add_parser(
        "backtest",
        help="Run QuantBuild backtest; optionally run quantmetrics_analytics on QuantLog output",
    )
    p_bt.add_argument("-c", "--config", required=True, help="YAML path relative to QUANTBUILD_ROOT")
    p_bt.add_argument("--days", "-d", type=int, default=None, dest="days")
    p_bt.add_argument("--start-date", dest="start_date", default=None, metavar="YYYY-MM-DD")
    p_bt.add_argument("--end-date", dest="end_date", default=None, metavar="YYYY-MM-DD")
    p_bt.add_argument(
        "--analyze",
        action="store_true",
        help="After a successful run, invoke quantmetrics_analytics on QuantLog JSONL (needs QUANTANALYTICS_ROOT)",
    )
    p_bt.add_argument(
        "--analyze-jsonl",
        type=Path,
        default=None,
        help="Explicit JSONL file for analytics (overrides auto-resolve from config)",
    )
    p_bt.add_argument(
        "--analyze-dir",
        type=Path,
        default=None,
        help="If set (and --analyze-jsonl omitted), pass this directory to analytics when consolidated JSONL cannot be resolved",
    )
    p_bt.add_argument(
        "--analyze-reports",
        default="all",
        help="Forwarded to analytics --reports (default: all)",
    )
    p_bt.add_argument("--analyze-output", type=Path, default=None, help="Forwarded to analytics -o")
    p_bt.add_argument(
        "--analyze-stdout",
        action="store_true",
        help="Forwarded to analytics --stdout (no output_rapport file)",
    )
    p_bt.add_argument(
        "--no-research-digest",
        action="store_true",
        help="Skip scripts/research_digest.py after a successful backtest (default: run digest)",
    )
    p_bt.set_defaults(func=cmd_backtest)

    p_an = sub.add_parser(
        "analyze",
        help="Run quantmetrics_analytics on QuantLog JSONL (QUANTANALYTICS_ROOT + QUANTBUILD_ROOT for Python/venv)",
    )
    p_an.add_argument("--jsonl", type=Path, default=None, metavar="PATH")
    p_an.add_argument("--glob", dest="glob_pattern", default=None, metavar="PATTERN")
    p_an.add_argument("--dir", dest="dir_path", type=Path, default=None, metavar="DIR")
    p_an.add_argument("--reports", default="all", metavar="LIST")
    p_an.add_argument("--output", "-o", type=Path, default=None, metavar="PATH")
    p_an.add_argument("--stdout", action="store_true")
    p_an.set_defaults(func=cmd_analyze)

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
