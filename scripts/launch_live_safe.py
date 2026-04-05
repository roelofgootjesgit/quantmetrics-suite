"""Safe live launcher for controlled cTrader demo runs.

Features:
- preflight checks
- optional recovery-first call into quantbridgev1
- controlled live subprocess launch
- heartbeat logging
- max runtime timeout
- graceful shutdown on signal/timeout
- final run summary with explicit exit codes
"""
from __future__ import annotations

import argparse
import importlib
import json
import logging
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

LOGGER = logging.getLogger("launch_live_safe")
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.quantbuild.config import load_config

DEFAULT_CONFIG = "configs/ctrader_quantbridge_openapi.yaml"

EXIT_OK = 0
EXIT_PREFLIGHT_FAILED = 2
EXIT_RECOVERY_FAILED = 3
EXIT_LIVE_FAILED = 4
EXIT_TIMEOUT = 124
EXIT_INTERRUPTED = 130


class ShutdownSignal:
    def __init__(self) -> None:
        self.reason: Optional[str] = None

    def set(self, reason: str) -> None:
        if self.reason is None:
            self.reason = reason


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _setup_logging(log_file: Path) -> None:
    log_file.parent.mkdir(parents=True, exist_ok=True)
    handlers: List[logging.Handler] = [
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(log_file, encoding="utf-8"),
    ]
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        handlers=handlers,
    )


def _load_env_file(path: Path) -> Dict[str, str]:
    values: Dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if key and value:
            values[key] = value
    return values


def _read_bridge_env(bridge_root: Path) -> Dict[str, str]:
    # Keep .env precedence to avoid stale local overrides.
    local_env = _load_env_file(bridge_root / "local.env")
    dot_env = _load_env_file(bridge_root / ".env")
    merged = dict(local_env)
    merged.update(dot_env)
    return merged


def _token_present(token: str) -> bool:
    return bool(token and len(token.strip()) >= 20)


def _resolve_credentials(cfg: Dict[str, object], bridge_env: Dict[str, str]) -> Dict[str, str]:
    broker = cfg.get("broker", {}) if isinstance(cfg.get("broker", {}), dict) else {}
    broker = broker if isinstance(broker, dict) else {}

    account_id = str(
        os.getenv("CTRADER_ACCOUNT_ID")
        or broker.get("account_id", "")
        or bridge_env.get("CTRADER_ACCOUNT_ID", "")
    ).strip()
    access_token = str(
        os.getenv("CTRADER_ACCESS_TOKEN")
        or broker.get("access_token", "")
        or bridge_env.get("CTRADER_ACCESS_TOKEN", "")
    ).strip()
    client_id = str(
        os.getenv("CTRADER_CLIENT_ID")
        or broker.get("client_id", "")
        or bridge_env.get("CTRADER_CLIENT_ID", "")
    ).strip()
    client_secret = str(
        os.getenv("CTRADER_CLIENT_SECRET")
        or broker.get("client_secret", "")
        or bridge_env.get("CTRADER_CLIENT_SECRET", "")
    ).strip()

    return {
        "account_id": account_id,
        "access_token": access_token,
        "client_id": client_id,
        "client_secret": client_secret,
    }


def _check_account_unpaused(
    bridge_root: Path,
    account_state_file: str,
    account_id: str,
) -> Tuple[bool, str]:
    state_path = Path(account_state_file)
    if not state_path.is_absolute():
        state_path = bridge_root / state_path
    if not state_path.exists():
        return False, f"account state file missing: {state_path}"
    try:
        raw = json.loads(state_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return False, f"cannot parse account state file: {exc}"
    if not isinstance(raw, dict):
        return False, "account state file is not a JSON object"
    entry = raw.get(str(account_id))
    if not isinstance(entry, dict):
        return False, f"no account state entry for account_id={account_id}"
    status = str(entry.get("status", "")).strip().lower()
    if status in {"paused", "breached", "disabled"}:
        reason = str(entry.get("reason", "")).strip() or status
        return False, f"account not tradable (status={status}, reason={reason})"
    return True, f"account state eligible (status={status or 'unknown'})"


def _preflight(args: argparse.Namespace) -> Tuple[bool, List[str], List[str], Dict[str, str], Dict[str, object]]:
    errors: List[str] = []
    warnings: List[str] = []

    cfg_path = Path(args.config)
    if not cfg_path.is_absolute():
        cfg_path = ROOT / cfg_path
    if not cfg_path.exists():
        errors.append(f"config not found: {cfg_path}")
        return False, errors, warnings, {}, {}

    cfg = load_config(cfg_path)
    broker = cfg.get("broker", {}) if isinstance(cfg.get("broker", {}), dict) else {}
    broker = broker if isinstance(broker, dict) else {}

    provider = str(broker.get("provider", "")).lower()
    if provider != "ctrader":
        errors.append(f"broker provider must be ctrader, got '{provider or 'missing'}'")

    if bool(broker.get("mock_mode", True)):
        errors.append("broker.mock_mode must be false for live launch")

    bridge_root = Path(args.bridge_root)
    if not bridge_root.is_absolute():
        bridge_root = ROOT / bridge_root
    bridge_src = bridge_root / "src"
    if not bridge_src.exists():
        errors.append(f"quantBridge src path not found: {bridge_src}")
    else:
        if str(bridge_src) not in sys.path:
            sys.path.insert(0, str(bridge_src))
        try:
            importlib.import_module("quantbridge.execution.brokers.ctrader_broker")
        except Exception as exc:
            errors.append(f"quantBridge import failed: {exc}")

    bridge_env = _read_bridge_env(bridge_root)
    creds = _resolve_credentials(cfg, bridge_env)
    if not creds["account_id"]:
        errors.append("missing CTRADER_ACCOUNT_ID (env/config/.env)")
    if not _token_present(creds["access_token"]):
        errors.append("missing or invalid CTRADER_ACCESS_TOKEN (env/config/.env)")
    if not creds["client_id"]:
        errors.append("missing CTRADER_CLIENT_ID (env/config/.env)")
    if not creds["client_secret"]:
        errors.append("missing CTRADER_CLIENT_SECRET (env/config/.env)")

    if args.require_unpaused:
        ok, message = _check_account_unpaused(
            bridge_root=bridge_root,
            account_state_file=args.account_state_file,
            account_id=creds.get("account_id", ""),
        )
        if not ok:
            errors.append(message)
        else:
            warnings.append(message)

    if args.run_recovery_first:
        recovery_script = bridge_root / "scripts" / "recover_execution_state.py"
        if not recovery_script.exists():
            errors.append(f"recovery script not found: {recovery_script}")
        recovery_cfg = Path(args.recovery_config)
        if not recovery_cfg.is_absolute():
            recovery_cfg = bridge_root / recovery_cfg
        if not recovery_cfg.exists():
            errors.append(f"recovery config not found: {recovery_cfg}")

    return len(errors) == 0, errors, warnings, creds, cfg


def _run_recovery(args: argparse.Namespace, bridge_root: Path, log_file: Path) -> int:
    recovery_cfg = Path(args.recovery_config)
    if not recovery_cfg.is_absolute():
        recovery_cfg = bridge_root / recovery_cfg
    cmd = [
        sys.executable,
        str(bridge_root / "scripts" / "recover_execution_state.py"),
        "--config",
        str(recovery_cfg),
        "--mode",
        "openapi",
    ]
    LOGGER.info("Running recovery-first: %s", " ".join(cmd))
    result = subprocess.run(
        cmd,
        cwd=str(bridge_root),
        text=True,
        capture_output=True,
        check=False,
    )
    if result.stdout:
        LOGGER.info("Recovery stdout:\n%s", result.stdout.strip())
    if result.stderr:
        LOGGER.warning("Recovery stderr:\n%s", result.stderr.strip())
    LOGGER.info("Recovery exit code: %s", result.returncode)
    return int(result.returncode)


def _stop_process(proc: subprocess.Popen, grace_seconds: int) -> str:
    if proc.poll() is not None:
        return "already_stopped"
    proc.terminate()
    try:
        proc.wait(timeout=grace_seconds)
        return "terminated"
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5)
        return "killed"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Safe launcher for quantbuild live mode.")
    parser.add_argument("--config", default=DEFAULT_CONFIG, help="Quantbuild config path")
    parser.add_argument("--max-runtime-seconds", type=int, default=1800)
    parser.add_argument("--heartbeat-seconds", type=int, default=30)
    parser.add_argument("--log-file", default="", help="Path to wrapper log file")
    parser.add_argument("--bridge-root", default=str(ROOT.parent / "quantbridgev1"))
    parser.add_argument("--run-recovery-first", action="store_true", default=True)
    parser.add_argument("--skip-recovery", action="store_true", help="Skip recovery-first step")
    parser.add_argument("--recovery-config", default="configs/ctrader_icmarkets_demo.yaml")
    parser.add_argument("--require-unpaused", action="store_true")
    parser.add_argument("--account-state-file", default="state/account_states.json")
    parser.add_argument("--dry-launch", action="store_true", help="Run preflight only; do not start live process")
    parser.add_argument("--shutdown-grace-seconds", type=int, default=20)
    args = parser.parse_args()
    if args.skip_recovery:
        args.run_recovery_first = False
    args.max_runtime_seconds = max(1, int(args.max_runtime_seconds))
    args.heartbeat_seconds = max(5, int(args.heartbeat_seconds))
    args.shutdown_grace_seconds = max(5, int(args.shutdown_grace_seconds))
    return args


def main() -> int:
    args = _parse_args()
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    log_file = Path(args.log_file) if args.log_file else (ROOT / "logs" / f"safe_live_launch_{ts}.log")
    if not log_file.is_absolute():
        log_file = ROOT / log_file
    _setup_logging(log_file)

    shutdown = ShutdownSignal()

    def _signal_handler(signum, _frame) -> None:
        name = signal.Signals(signum).name
        shutdown.set(f"signal:{name}")
        LOGGER.warning("Shutdown signal received: %s", name)

    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    bridge_root = Path(args.bridge_root)
    if not bridge_root.is_absolute():
        bridge_root = ROOT / bridge_root
    launch_started_at = time.time()

    ok, errors, warnings, creds, cfg = _preflight(args)
    preflight_report = {
        "timestamp": _utc_now(),
        "ok": ok,
        "errors": errors,
        "warnings": warnings,
        "provider": str((cfg.get("broker", {}) or {}).get("provider", "")) if cfg else "",
        "mock_mode": bool((cfg.get("broker", {}) or {}).get("mock_mode", True)) if cfg else None,
        "account_id": creds.get("account_id", ""),
        "token_present": _token_present(creds.get("access_token", "")),
        "client_id_present": bool(creds.get("client_id")),
        "client_secret_present": bool(creds.get("client_secret")),
        "bridge_root": str(bridge_root),
        "config": str(args.config),
        "log_file": str(log_file),
    }
    LOGGER.info("Preflight report: %s", json.dumps(preflight_report, indent=2))

    if not ok:
        print(json.dumps({"ok": False, "stage": "preflight", "errors": errors, "log_file": str(log_file)}, indent=2))
        return EXIT_PREFLIGHT_FAILED

    if args.dry_launch:
        print(json.dumps({"ok": True, "stage": "dry_launch", "log_file": str(log_file)}, indent=2))
        return EXIT_OK

    if args.run_recovery_first:
        recovery_rc = _run_recovery(args, bridge_root=bridge_root, log_file=log_file)
        if recovery_rc != 0:
            print(
                json.dumps(
                    {
                        "ok": False,
                        "stage": "recovery",
                        "exit_code": recovery_rc,
                        "log_file": str(log_file),
                    },
                    indent=2,
                )
            )
            return EXIT_RECOVERY_FAILED

    live_cmd = [
        sys.executable,
        "-m",
        "src.quantbuild.app",
        "--config",
        str(args.config),
        "live",
        "--real",
    ]
    child_env = os.environ.copy()
    child_env["CTRADER_ACCOUNT_ID"] = creds.get("account_id", "")
    child_env["CTRADER_ACCESS_TOKEN"] = creds.get("access_token", "")
    child_env["CTRADER_CLIENT_ID"] = creds.get("client_id", "")
    child_env["CTRADER_CLIENT_SECRET"] = creds.get("client_secret", "")
    child_env.setdefault("QUANTBRIDGE_SRC_PATH", str(bridge_root / "src"))
    LOGGER.info("Starting live subprocess: %s", " ".join(live_cmd))
    with log_file.open("a", encoding="utf-8") as live_log:
        live_log.write("\n=== LIVE SUBPROCESS START ===\n")
        live_log.flush()
        proc = subprocess.Popen(
            live_cmd,
            cwd=str(ROOT),
            stdout=live_log,
            stderr=subprocess.STDOUT,
            text=True,
            env=child_env,
        )

        heartbeat_next = time.time() + args.heartbeat_seconds
        reason = "completed"
        exit_code = None
        while True:
            now = time.time()
            elapsed = int(now - launch_started_at)
            child_rc = proc.poll()
            if child_rc is not None:
                exit_code = int(child_rc)
                reason = "completed"
                break
            if shutdown.reason:
                reason = shutdown.reason
                action = _stop_process(proc, grace_seconds=args.shutdown_grace_seconds)
                LOGGER.warning("Stop requested (%s), child stop action=%s", shutdown.reason, action)
                exit_code = proc.poll()
                break
            if elapsed >= args.max_runtime_seconds:
                reason = "timeout"
                action = _stop_process(proc, grace_seconds=args.shutdown_grace_seconds)
                LOGGER.warning("Max runtime reached, child stop action=%s", action)
                exit_code = proc.poll()
                break
            if now >= heartbeat_next:
                LOGGER.info(
                    "Heartbeat | pid=%s | elapsed=%ss | max=%ss | status=running",
                    proc.pid,
                    elapsed,
                    args.max_runtime_seconds,
                )
                heartbeat_next = now + args.heartbeat_seconds
            time.sleep(1.0)

        total_elapsed = int(time.time() - launch_started_at)
        summary = {
            "ok": reason == "completed" and int(exit_code or 0) == 0,
            "reason": reason,
            "live_exit_code": int(exit_code or 0),
            "elapsed_seconds": total_elapsed,
            "max_runtime_seconds": int(args.max_runtime_seconds),
            "account_id": creds.get("account_id", ""),
            "config": str(args.config),
            "log_file": str(log_file),
            "finished_at": _utc_now(),
        }
        LOGGER.info("Final summary: %s", json.dumps(summary, indent=2))
        print(json.dumps(summary, indent=2))

        if reason.startswith("signal:"):
            return EXIT_INTERRUPTED
        if reason == "timeout":
            return EXIT_TIMEOUT
        return EXIT_OK if int(exit_code or 0) == 0 else EXIT_LIVE_FAILED


if __name__ == "__main__":
    raise SystemExit(main())
