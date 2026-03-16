"""Logging setup from config with optional file output."""
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict


def _log_path_with_timestamp(file_path: str) -> Path:
    path = Path(file_path)
    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    base = (path.stem if path.suffix else path.name) or "quantbuild"
    return path.parent / f"{base}_{stamp}.log"


def setup_logging(cfg: Dict[str, Any] | None = None) -> None:
    cfg = cfg or {}
    log_cfg = cfg.get("logging", {})
    level = log_cfg.get("level", "INFO")
    fmt = log_cfg.get("format", "%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    level_value = getattr(logging, level.upper(), logging.INFO)

    logging.basicConfig(level=level_value, format=fmt, stream=sys.stdout, force=True)
    root = logging.getLogger()

    file_path = os.environ.get("OCLW_LOG_FILE") or log_cfg.get("file_path")
    if file_path:
        path = Path(file_path) if os.environ.get("OCLW_LOG_FILE") else _log_path_with_timestamp(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            fh = logging.FileHandler(path, mode="a", encoding="utf-8")
            fh.setLevel(level_value)
            fh.setFormatter(logging.Formatter(fmt))
            root.addHandler(fh)
        except OSError as e:
            root.warning("Could not open log file %s: %s", path, e)
