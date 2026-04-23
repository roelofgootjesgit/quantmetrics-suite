from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

import yaml

ROOT = Path(__file__).resolve().parents[1]


def load_env_file(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    if not path.exists():
        return env
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if key and value:
            env[key] = value
    return env


def load_config(path: str) -> dict:
    cfg_path = Path(path)
    if not cfg_path.is_absolute():
        cfg_path = ROOT / cfg_path
    with open(cfg_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def normalize_env_key(account_id: str, key: str) -> str:
    base = account_id.upper().replace("-", "_").replace(" ", "_")
    return f"QB_ACCOUNT_{base}_{key}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate account policy IDs against available account ENV credentials.")
    parser.add_argument("--config", default="configs/accounts_baseline.yaml")
    parser.add_argument("--env-file", default="local.env")
    parser.add_argument("--require-secrets", action="store_true")
    args = parser.parse_args()

    config = load_config(args.config)
    accounts = config.get("accounts", []) or []
    file_env = load_env_file(ROOT / args.env_file)
    runtime_env = {k: v for k, v in os.environ.items() if v}
    merged_env = {**file_env, **runtime_env}

    checks = []
    ok = True
    for raw in accounts:
        account_id = str(raw.get("account_id", "")).strip()
        if not account_id:
            continue
        mode_key = normalize_env_key(account_id, "MODE")
        account_key = normalize_env_key(account_id, "CTRADER_ACCOUNT_ID")
        token_key = normalize_env_key(account_id, "CTRADER_ACCESS_TOKEN")
        client_key = normalize_env_key(account_id, "CTRADER_CLIENT_ID")
        secret_key = normalize_env_key(account_id, "CTRADER_CLIENT_SECRET")

        mode = (merged_env.get(mode_key) or "openapi").lower()
        missing: list[str] = []
        present: list[str] = []
        for key in [mode_key, account_key, token_key, client_key, secret_key]:
            if key in merged_env:
                present.append(key)

        if mode == "mock":
            # mock mode account can run without broker credentials
            checks.append(
                {
                    "account_id": account_id,
                    "mode": mode,
                    "ok": True,
                    "missing": [],
                    "present": present,
                }
            )
            continue

        required = [account_key, token_key]
        if args.require_secrets:
            required += [client_key, secret_key]
        for key in required:
            if key not in merged_env:
                missing.append(key)

        item_ok = len(missing) == 0
        ok = ok and item_ok
        checks.append(
            {
                "account_id": account_id,
                "mode": mode,
                "ok": item_ok,
                "missing": missing,
                "present": present,
            }
        )

    output = {
        "ok": ok,
        "config": args.config,
        "env_file": args.env_file,
        "require_secrets": bool(args.require_secrets),
        "checks": checks,
    }
    print(json.dumps(output, indent=2))
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
