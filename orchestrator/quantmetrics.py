"""
Minimal QuantMetrics suite orchestrator: resolve repo roots from .env and run
QuantBuild / QuantBridge / QuantLog subprocesses with the correct cwd and PYTHONPATH.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


_ORCH_DIR = Path(__file__).resolve().parent
_ENV_CANDIDATES = (_ORCH_DIR / ".env", _ORCH_DIR.parent / ".env")


def _load_dotenv() -> None:
    for p in _ENV_CANDIDATES:
        if not p.is_file():
            continue
        for raw in p.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = val
        break


def _require_dir(name: str) -> Path:
    raw = os.environ.get(name, "").strip()
    if not raw:
        print(f"Missing env {name}. Copy orchestrator/config.example.env to orchestrator/.env", file=sys.stderr)
        sys.exit(2)
    p = Path(os.path.expandvars(raw)).expanduser().resolve()
    if not p.is_dir():
        print(f"{name} is not a directory: {p}", file=sys.stderr)
        sys.exit(2)
    return p


def _python() -> str:
    return os.environ.get("PYTHON", "python").strip() or "python"


def _run(cmd: list[str], *, cwd: Path, env: dict[str, str] | None = None) -> int:
    print("+", " ".join(cmd), file=sys.stderr)
    print("(cwd)", cwd, file=sys.stderr)
    r = subprocess.run(cmd, cwd=str(cwd), env=env)
    return int(r.returncode)


def cmd_check(_: argparse.Namespace) -> int:
    _load_dotenv()
    b = _require_dir("QUANTBUILD_ROOT")
    br = _require_dir("QUANTBRIDGE_ROOT")
    lg = _require_dir("QUANTLOG_ROOT")
    events = _events_root()
    print("QUANTBUILD_ROOT:", b)
    print("QUANTBRIDGE_ROOT:", br)
    print("QUANTLOG_ROOT:", lg)
    print("QUANTLOG_EVENTS_ROOT:", events)
    return 0


def _events_root() -> Path:
    _load_dotenv()
    raw = os.environ.get("QUANTLOG_EVENTS_ROOT", "").strip()
    if raw:
        return Path(os.path.expandvars(raw)).expanduser().resolve()
    return _require_dir("QUANTBUILD_ROOT") / "data" / "quantlog_events"


def _env_with_pythonpath(extra: str | None) -> dict[str, str]:
    e = os.environ.copy()
    if extra:
        prev = e.get("PYTHONPATH", "")
        e["PYTHONPATH"] = extra if not prev else f"{extra}{os.pathsep}{prev}"
    return e


def cmd_build(args: argparse.Namespace) -> int:
    _load_dotenv()
    root = _require_dir("QUANTBUILD_ROOT")
    cfg = args.config or os.environ.get("QUANTBUILD_CONFIG", "configs/strict_prod_v2.yaml")
    py = _python()
    cmd = [py, "-m", "src.quantbuild.app", "--config", cfg, "live"]
    if args.real:
        cmd.append("--real")
    cmd.extend(args.extra)
    return _run(cmd, cwd=root, env=_env_with_pythonpath(str(root)))


def cmd_bridge(args: argparse.Namespace) -> int:
    _load_dotenv()
    root = _require_dir("QUANTBRIDGE_ROOT")
    cfg = args.config or os.environ.get("QUANTBRIDGE_CONFIG", "configs/ctrader_icmarkets_demo.yaml")
    py = _python()
    if args.sub == "smoke":
        cmd = [py, "scripts/ctrader_smoke.py", "--config", cfg]
        if args.mode:
            cmd.extend(["--mode", args.mode])
        cmd.extend(args.extra)
        return _run(cmd, cwd=root)
    if args.sub == "regression":
        cmd = [py, "scripts/run_regression_suite.py"]
        cmd.extend(args.extra)
        return _run(cmd, cwd=root)
    raise SystemExit("internal: unknown bridge subcommand")


def cmd_log(args: argparse.Namespace) -> int:
    _load_dotenv()
    root = _require_dir("QUANTLOG_ROOT")
    py = _python()
    ql_src = str(root / "src")
    cmd = [py, "-m", "quantlog.cli", args.sub]
    for a in args.log_args:
        cmd.append(a)
    return _run(cmd, cwd=root, env=_env_with_pythonpath(ql_src))


def cmd_notify(args: argparse.Namespace) -> int:
    """Suite lifecycle Telegram via QuantBuild (monitoring.telegram in YAML)."""
    _load_dotenv()
    root = _require_dir("QUANTBUILD_ROOT")
    cfg = args.config or os.environ.get("QUANTBUILD_CONFIG", "configs/strict_prod_v2.yaml")
    py = _python()
    cmd = [
        py,
        "-m",
        "src.quantbuild.app",
        "--config",
        cfg,
        "suite-notify",
        args.event,
        *args.components,
    ]
    if getattr(args, "reason", None) and str(args.reason).strip():
        cmd.extend(["--reason", str(args.reason).strip()])
    return _run(cmd, cwd=root, env=_env_with_pythonpath(str(root)))


def cmd_post_run(args: argparse.Namespace) -> int:
    _load_dotenv()
    day = args.date.strip()
    path = _events_root() / day
    if not path.is_dir():
        print(f"Event day folder missing: {path}", file=sys.stderr)
        return 2
    py = _python()
    ql_root = _require_dir("QUANTLOG_ROOT")
    ql_src = str(ql_root / "src")
    env = _env_with_pythonpath(ql_src)
    base = [py, "-m", "quantlog.cli"]

    for sub in ("validate-events", "summarize-day", "score-run"):
        rc = _run(base + [sub, "--path", str(path)], cwd=ql_root, env=env)
        if rc != 0:
            return rc
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="quantmetrics",
        description="QuantMetrics OS — minimal multi-repo orchestrator",
    )
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("check", help="Print resolved paths from .env").set_defaults(func=cmd_check)

    pb = sub.add_parser("build", help="Run QuantBuild live (subprocess)")
    pb.add_argument(
        "-c",
        "--config",
        default=None,
        help="Config YAML relative to QuantBuild root (default: $QUANTBUILD_CONFIG)",
    )
    pb.add_argument(
        "--real",
        action="store_true",
        help="Real trading (forwards --real to QuantBuild; default is dry/paper)",
    )
    pb.add_argument(
        "extra",
        nargs=argparse.REMAINDER,
        help="Extra args after -- (passed to quantbuild)",
    )
    pb.set_defaults(func=cmd_build)

    br = sub.add_parser("bridge", help="Run QuantBridge scripts")
    br_sub = br.add_subparsers(dest="sub", required=True)
    sm = br_sub.add_parser("smoke", help="ctrader_smoke.py")
    sm.add_argument("--config", "-c", default=None, help="YAML under QuantBridge root")
    sm.add_argument("--mode", default=None, help="e.g. mock | openapi")
    sm.add_argument("extra", nargs=argparse.REMAINDER, help="Extra args for smoke script")
    sm.set_defaults(func=cmd_bridge)

    reg = br_sub.add_parser("regression", help="run_regression_suite.py")
    reg.add_argument("extra", nargs=argparse.REMAINDER, help="Extra args for regression script")
    reg.set_defaults(func=cmd_bridge)

    lg = sub.add_parser(
        "log",
        help="QuantLog CLI (pass-through). Example: quantmetrics log -- summarize-day --path <dir>",
    )
    lg.add_argument("sub", help="quantlog.cli subcommand, e.g. validate-events")
    lg.add_argument(
        "log_args",
        nargs=argparse.REMAINDER,
        help="Arguments for that subcommand (omit leading -- if using quantmetrics log --)",
    )
    lg.set_defaults(func=cmd_log)

    pr = sub.add_parser(
        "post-run",
        help="validate-events + summarize-day + score-run on <events_root>/<YYYY-MM-DD>",
    )
    pr.add_argument("date", help="UTC date folder name, e.g. 2026-03-29")
    pr.set_defaults(func=cmd_post_run)

    nt = sub.add_parser(
        "notify",
        help="Telegram suite start/stop (QuantBuild monitoring.telegram); list component labels",
    )
    nt.add_argument("event", choices=["start", "stop"], help="Suite lifecycle")
    nt.add_argument(
        "components",
        nargs="+",
        metavar="COMPONENT",
        help="e.g. build bridge log (labels only, for the message)",
    )
    nt.add_argument(
        "-c",
        "--config",
        default=None,
        help="QuantBuild YAML relative to QUANTBUILD_ROOT (default: $QUANTBUILD_CONFIG)",
    )
    nt.add_argument("--reason", default="", help="Optional note (typically for stop)")
    nt.set_defaults(func=cmd_notify)

    return p


def main() -> int:
    _load_dotenv()
    parser = build_parser()
    args = parser.parse_args()
    if getattr(args, "extra", None) and args.extra and args.extra[0] == "--":
        args.extra = args.extra[1:]
    if getattr(args, "sub", None) == "smoke" and getattr(args, "extra", None):
        if args.extra and args.extra[0] == "--":
            args.extra = args.extra[1:]
    if getattr(args, "sub", None) == "regression" and getattr(args, "extra", None):
        if args.extra and args.extra[0] == "--":
            args.extra = args.extra[1:]
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
