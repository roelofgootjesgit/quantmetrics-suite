from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import yaml

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from quantbridge.accounts.account_state_machine import AccountStateMachine


def load_accounts(path: str) -> list[dict]:
    cfg_path = Path(path)
    if not cfg_path.is_absolute():
        cfg_path = ROOT / cfg_path
    if not cfg_path.exists():
        return []
    with open(cfg_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data.get("accounts", []) or []


def main() -> int:
    parser = argparse.ArgumentParser(description="Control account governance states.")
    parser.add_argument("--state-file", default="state/account_states.json")
    parser.add_argument("--accounts-config", default="configs/accounts_baseline.yaml")
    parser.add_argument(
        "action",
        choices=["status", "pause", "resume", "breach", "set-health", "record-risk-block"],
    )
    parser.add_argument("--account-id", default="")
    parser.add_argument("--mode", choices=["demo", "challenge", "funded"], default="demo")
    parser.add_argument("--reason", default="")
    parser.add_argument("--paused-by", default="manual")
    parser.add_argument("--breach-type", default="manual")
    parser.add_argument("--health", default="unknown")
    parser.add_argument("--risk-block", default="")
    args = parser.parse_args()

    machine = AccountStateMachine(path=args.state_file)

    if args.action == "status":
        accounts = load_accounts(args.accounts_config)
        rows = []
        if args.account_id:
            state = machine.get_state(args.account_id)
            rows.append(state.__dict__)
        else:
            ids = [str(a.get("account_id", "")) for a in accounts if str(a.get("account_id", "")).strip()]
            if not ids:
                store_raw = machine.store.load()
                ids = sorted(store_raw.keys())
            for account_id in ids:
                rows.append(machine.get_state(account_id). __dict__)
        print(json.dumps({"ok": True, "states": rows}, indent=2))
        return 0

    if not args.account_id:
        print(json.dumps({"ok": False, "error": "missing_account_id"}, indent=2))
        return 2

    if args.action == "pause":
        state = machine.pause(account_id=args.account_id, reason=args.reason or "manual_pause", paused_by=args.paused_by)
    elif args.action == "resume":
        state = machine.resume(account_id=args.account_id, mode=args.mode, reason=args.reason or "manual_resume")
    elif args.action == "breach":
        state = machine.breach(account_id=args.account_id, reason=args.reason or "manual_breach", breach_type=args.breach_type)
    elif args.action == "set-health":
        state = machine.set_health_state(account_id=args.account_id, health_state=args.health, reason=args.reason)
    elif args.action == "record-risk-block":
        block = args.risk_block or args.reason or "manual_risk_block"
        state = machine.record_risk_block(account_id=args.account_id, block_reason=block)
    else:
        print(json.dumps({"ok": False, "error": "unsupported_action"}, indent=2))
        return 2

    print(json.dumps({"ok": True, "state": state.__dict__}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
