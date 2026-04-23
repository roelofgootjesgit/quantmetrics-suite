"""Load strategy plugins from account config (Layer 4 → Layer 2)."""
from __future__ import annotations

import importlib
import re
from typing import Any, List, Type

from quantbuild_v2.strategies.base import Strategy

# Only load strategy implementations from our package tree (config-driven import is still code execution).
_STRATEGY_MODULE_RE = re.compile(r"^quantbuild_v2\.strategies(\.[a-zA-Z0-9_]+)*$")


def _import_class(path: str) -> Type[Strategy]:
    """Import `module.sub:ClassName` and return the class."""
    if ":" not in path:
        raise ValueError(f"strategy class path must be 'module:Class', got {path!r}")
    mod_name, _, cls_name = path.partition(":")
    if not _STRATEGY_MODULE_RE.fullmatch(mod_name):
        raise ValueError(
            f"strategy module must match quantbuild_v2.strategies.*, got module {mod_name!r}"
        )
    if not cls_name.isidentifier():
        raise ValueError(f"strategy class name must be a valid identifier, got {cls_name!r}")
    module = importlib.import_module(mod_name)
    obj = getattr(module, cls_name, None)
    if obj is None or not isinstance(obj, type) or not issubclass(obj, Strategy):
        raise TypeError(f"{path!r} must resolve to a Strategy subclass")
    return obj


def load_strategies(account_config: dict[str, Any]) -> List[Strategy]:
    """
    Read `strategies` list from account YAML (dict after parse).

    Each item: { id, class, enabled?, config? }
    """
    raw = account_config.get("strategies") or []
    out: List[Strategy] = []
    for item in raw:
        if not item.get("enabled", True):
            continue
        sid = item.get("id")
        class_path = item.get("class")
        if not sid or not class_path:
            raise ValueError("each strategy needs 'id' and 'class'")
        cls = _import_class(class_path)
        strat_cfg = dict(item.get("config") or {})
        instance = cls(strategy_id=sid, config=strat_cfg)
        out.append(instance)
    return out
