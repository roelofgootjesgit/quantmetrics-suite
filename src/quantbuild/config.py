"""Configuration loader: YAML + env overrides + deep merge."""
import os
from pathlib import Path
from typing import Any, Dict

import yaml
from dotenv import load_dotenv

load_dotenv(override=True)

_DEFAULT_PATH = Path(__file__).resolve().parents[2] / "configs" / "default.yaml"


def load_config(path: str | Path | None = None) -> Dict[str, Any]:
    """Load config from YAML; merge with default; override from env."""
    default: Dict[str, Any] = {}
    if _DEFAULT_PATH.exists():
        with open(_DEFAULT_PATH, "r", encoding="utf-8") as f:
            default = yaml.safe_load(f) or {}

    cfg_path = path or os.getenv("CONFIG_PATH") or _DEFAULT_PATH
    cfg_path = Path(cfg_path)
    if not cfg_path.is_absolute():
        base = Path(__file__).resolve().parents[2]
        cfg_path = base / cfg_path

    merged = dict(default)
    if cfg_path.exists() and cfg_path != _DEFAULT_PATH:
        with open(cfg_path, "r", encoding="utf-8") as f:
            overrides = yaml.safe_load(f) or {}
        _deep_merge(merged, overrides)

    if os.getenv("DATA_PATH"):
        merged.setdefault("data", {})["base_path"] = os.getenv("DATA_PATH")
    if os.getenv("CACHE_TTL_HOURS"):
        merged.setdefault("data", {})["cache_ttl_hours"] = int(os.getenv("CACHE_TTL_HOURS", "24"))

    # Broker env overrides (safe for both oanda and ctrader profiles)
    broker = merged.setdefault("broker", {})
    if os.getenv("OANDA_ACCOUNT_ID"):
        broker["account_id"] = os.getenv("OANDA_ACCOUNT_ID")
    if os.getenv("OANDA_TOKEN"):
        broker["token"] = os.getenv("OANDA_TOKEN")
    if os.getenv("CTRADER_ACCOUNT_ID"):
        broker["account_id"] = os.getenv("CTRADER_ACCOUNT_ID")
    if os.getenv("CTRADER_ACCESS_TOKEN"):
        broker["access_token"] = os.getenv("CTRADER_ACCESS_TOKEN")
    if os.getenv("CTRADER_CLIENT_ID"):
        broker["client_id"] = os.getenv("CTRADER_CLIENT_ID")
    if os.getenv("CTRADER_CLIENT_SECRET"):
        broker["client_secret"] = os.getenv("CTRADER_CLIENT_SECRET")

    # Telegram env overrides (prefer env over committed YAML secrets)
    monitoring = merged.setdefault("monitoring", {})
    telegram = monitoring.setdefault("telegram", {})
    if os.getenv("TELEGRAM_ENABLED"):
        telegram["enabled"] = os.getenv("TELEGRAM_ENABLED", "false").strip().lower() in {
            "1", "true", "yes", "on",
        }
    if os.getenv("TELEGRAM_BOT_TOKEN"):
        telegram["bot_token"] = os.getenv("TELEGRAM_BOT_TOKEN")
    if os.getenv("TELEGRAM_CHAT_ID"):
        telegram["chat_id"] = os.getenv("TELEGRAM_CHAT_ID")
    if os.getenv("TELEGRAM_REPORT_INTERVAL_SECONDS"):
        telegram.setdefault("report", {})["interval_seconds"] = int(
            os.getenv("TELEGRAM_REPORT_INTERVAL_SECONDS", "3600")
        )

    return merged


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> None:
    for k, v in override.items():
        if k in base and isinstance(base[k], dict) and isinstance(v, dict):
            _deep_merge(base[k], v)
        else:
            base[k] = v
