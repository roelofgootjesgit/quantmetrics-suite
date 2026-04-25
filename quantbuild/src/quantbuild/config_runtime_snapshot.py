"""Effective runtime config for run artifacts (merged YAML + env), safe to archive.

The file copied as ``config_snapshot.yaml`` is only the CLI YAML path (often thin
``extends`` wrappers). This module serializes the *merged* dict used by the engine.
"""
from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import yaml

REDACTED = "<redacted>"

# Key names (substring match, lowercased) whose string values must not be archived.
_SENSITIVE_KEY_MARKERS = (
    "password",
    "secret",
    "token",
    "api_key",
    "private_key",
    "access_token",
)


def _sensitive_key(name: str) -> bool:
    n = name.lower()
    return any(m in n for m in _SENSITIVE_KEY_MARKERS)


def redact_tree(obj: Any) -> Any:
    if isinstance(obj, dict):
        out: dict[Any, Any] = {}
        for k, v in obj.items():
            if isinstance(k, str) and _sensitive_key(k):
                out[k] = REDACTED
            else:
                out[k] = redact_tree(v)
        return out
    if isinstance(obj, list):
        return [redact_tree(x) for x in obj]
    return obj


def runtime_config_for_artifact(cfg: dict[str, Any]) -> dict[str, Any]:
    data = copy.deepcopy(cfg)
    for k in list(data.keys()):
        if isinstance(k, str) and k.startswith("_quantbuild"):
            del data[k]
    return redact_tree(data)


def write_runtime_config_yaml(cfg: dict[str, Any], path: str | Path) -> Path:
    """Write redacted merged config to ``path``; returns resolved path."""
    out = Path(path)
    snap = runtime_config_for_artifact(cfg)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        yaml.safe_dump(
            snap,
            f,
            default_flow_style=False,
            sort_keys=False,
            allow_unicode=True,
        )
    return out.resolve()
