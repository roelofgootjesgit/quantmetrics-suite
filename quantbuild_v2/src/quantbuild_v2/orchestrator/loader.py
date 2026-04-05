"""Load strategy plugins from account config (Layer 4 → Layer 2)."""
from __future__ import annotations

import importlib
from typing import Any, List, Type

from quantbuild_v2.strategies.base import Strategy


def _import_class(path: str) -> Type[Strategy]:
    """Import `module.sub:ClassName` and return the class."""
    if ":" not in path:
        raise ValueError(f"strategy class path must be 'module:Class', got {path!r}")
    mod_name, _, cls_name = path.partition(":")
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
