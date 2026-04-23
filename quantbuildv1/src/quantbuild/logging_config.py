"""Logging setup from config with optional file output."""
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict


def _log_path_with_timestamp(file_path: str, command: str | None = None) -> Path:
    """Build ``logs/<command>_quantbuild_<UTC-datetime>.log`` so each run is identifiable."""
    path = Path(file_path)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H-%M-%SZ")
    base = (path.stem if path.suffix else path.name) or "quantbuild"
    prefix = ""
    if command:
        prefix = command.replace("-", "_").strip("_") + "_"
    return path.parent / f"{prefix}{base}_{stamp}.log"


def setup_logging(cfg: Dict[str, Any] | None = None, *, command: str | None = None) -> None:
    cfg = cfg or {}
    log_cfg = cfg.get("logging", {})
    level = log_cfg.get("level", "INFO")
    fmt = log_cfg.get("format", "%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    level_value = getattr(logging, level.upper(), logging.INFO)

    logging.basicConfig(level=level_value, format=fmt, stream=sys.stdout, force=True)
    root = logging.getLogger()

    raw_path = os.environ.get("OCLW_LOG_FILE") or log_cfg.get("file_path")
    env_log_override = bool(os.environ.get("OCLW_LOG_FILE"))
    use_timestamp_suffix = bool(log_cfg.get("timestamp_suffix", True))

    if raw_path:
        if env_log_override:
            path = Path(raw_path)
        elif use_timestamp_suffix:
            path = _log_path_with_timestamp(raw_path, command=command)
        else:
            path = Path(raw_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            fh = logging.FileHandler(path, mode="a", encoding="utf-8")
            fh.setLevel(level_value)
            fh.setFormatter(logging.Formatter(fmt))
            root.addHandler(fh)
            print(f"[quantbuild] Log file: {path.resolve()}")
        except OSError as e:
            root.warning("Could not open log file %s: %s", path, e)
