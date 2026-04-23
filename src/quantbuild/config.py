"""Configuration loader: YAML + env overrides + deep merge."""
import os
from pathlib import Path
from typing import Any, Dict

import yaml
from dotenv import load_dotenv

load_dotenv(override=True)


def quantbuild_repo_root() -> Path:
    """Directory containing ``configs/default.yaml`` (QuantBuild checkout root).

    Walks upward from this file so layout stays correct if ``config.py`` moves
    within ``src/``. Falls back to two parents above this file (``src/quantbuild`` → repo root).
    """
    start = Path(__file__).resolve().parent
    for d in (start, *start.parents):
        if (d / "configs" / "default.yaml").is_file():
            return d
    return Path(__file__).resolve().parents[2]


_DEFAULT_PATH = quantbuild_repo_root() / "configs" / "default.yaml"


def _resolve_extends_path(raw: str, referencing_file: Path) -> Path:
    """Resolve ``extends`` path relative to the referencing YAML directory."""
    root = quantbuild_repo_root()
    p = Path(raw.strip())
    if p.is_absolute():
        return p
    cand = (referencing_file.resolve().parent / p).resolve()
    if cand.is_file():
        return cand
    alt = (root / "configs" / p.name).resolve()
    if alt.is_file():
        return alt
    alt2 = (root / p).resolve()
    return alt2


def _load_yaml_with_extends(path: Path, visited: set[Path]) -> Dict[str, Any]:
    """Load one YAML file and recursively merge ``extends`` parents (parent first, child wins)."""
    path = path.resolve()
    if path in visited:
        raise ValueError(f"Configuration extends cycle detected at {path}")
    visited.add(path)
    if not path.is_file():
        raise FileNotFoundError(f"Config file not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    extends_raw = raw.pop("extends", None)
    merged_file: Dict[str, Any] = {}
    if extends_raw:
        parent_path = _resolve_extends_path(str(extends_raw), path)
        parent_data = _load_yaml_with_extends(parent_path, visited)
        _deep_merge(merged_file, parent_data)
    _deep_merge(merged_file, raw)
    return merged_file


def load_config(path: str | Path | None = None) -> Dict[str, Any]:
    """Load config from YAML; merge with default; override from env."""
    default: Dict[str, Any] = {}
    if _DEFAULT_PATH.exists():
        with open(_DEFAULT_PATH, "r", encoding="utf-8") as f:
            default = yaml.safe_load(f) or {}

    cfg_path = path or os.getenv("CONFIG_PATH") or _DEFAULT_PATH
    cfg_path = Path(cfg_path)
    if not cfg_path.is_absolute():
        cfg_path = quantbuild_repo_root() / cfg_path

    merged = dict(default)
    if cfg_path.exists() and cfg_path != _DEFAULT_PATH:
        overrides = _load_yaml_with_extends(cfg_path, set())
        _deep_merge(merged, overrides)

    if os.getenv("DATA_PATH"):
        merged.setdefault("data", {})["base_path"] = os.getenv("DATA_PATH")
    if os.getenv("CACHE_TTL_HOURS"):
        merged.setdefault("data", {})["cache_ttl_hours"] = int(os.getenv("CACHE_TTL_HOURS", "24"))

    # News / AI env overrides
    news = merged.setdefault("news", {})
    if os.getenv("NEWSAPI_KEY"):
        news["newsapi_key"] = os.getenv("NEWSAPI_KEY")
    if os.getenv("FINNHUB_API_KEY"):
        news["finnhub_api_key"] = os.getenv("FINNHUB_API_KEY")
    if os.getenv("NEWSAPI_ENABLED"):
        news_sources = news.setdefault("sources", {})
        newsapi_cfg = news_sources.setdefault("newsapi", {})
        newsapi_cfg["enabled"] = os.getenv("NEWSAPI_ENABLED", "false").strip().lower() in {
            "1", "true", "yes", "on",
        }
    if os.getenv("FINNHUB_ENABLED"):
        news_sources = news.setdefault("sources", {})
        finnhub_cfg = news_sources.setdefault("finnhub", {})
        finnhub_cfg["enabled"] = os.getenv("FINNHUB_ENABLED", "false").strip().lower() in {
            "1", "true", "yes", "on",
        }
    if os.getenv("FINNHUB_CATEGORY"):
        news_sources = news.setdefault("sources", {})
        finnhub_cfg = news_sources.setdefault("finnhub", {})
        finnhub_cfg["category"] = os.getenv("FINNHUB_CATEGORY")
    if os.getenv("NEWSAPI_CATEGORIES"):
        categories = [
            c.strip() for c in os.getenv("NEWSAPI_CATEGORIES", "").split(",") if c.strip()
        ]
        if categories:
            news_sources = news.setdefault("sources", {})
            newsapi_cfg = news_sources.setdefault("newsapi", {})
            newsapi_cfg["categories"] = categories

    ai = merged.setdefault("ai", {})
    if os.getenv("OPENAI_API_KEY"):
        ai["openai_api_key"] = os.getenv("OPENAI_API_KEY")
    if os.getenv("OPENAI_MODEL"):
        ai["model"] = os.getenv("OPENAI_MODEL")

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
    if os.getenv("TELEGRAM_SYSTEM_LABEL"):
        telegram["system_label"] = os.getenv("TELEGRAM_SYSTEM_LABEL")
    if os.getenv("TELEGRAM_INSTANCE_LABEL"):
        telegram["instance_label"] = os.getenv("TELEGRAM_INSTANCE_LABEL")
    if os.getenv("TELEGRAM_REPORT_INTERVAL_SECONDS"):
        telegram.setdefault("report", {})["interval_seconds"] = int(
            os.getenv("TELEGRAM_REPORT_INTERVAL_SECONDS", "3600")
        )

    merged["_quantbuild_config_path"] = str(cfg_path.resolve())

    return merged


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> None:
    for k, v in override.items():
        if k in base and isinstance(base[k], dict) and isinstance(v, dict):
            _deep_merge(base[k], v)
        else:
            base[k] = v
