"""Configuration loader: YAML + env overrides + deep merge."""
import os
from pathlib import Path
from typing import Any, Dict

import yaml
from dotenv import load_dotenv

load_dotenv()

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

    return merged


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> None:
    for k, v in override.items():
        if k in base and isinstance(base[k], dict) and isinstance(v, dict):
            _deep_merge(base[k], v)
        else:
            base[k] = v
