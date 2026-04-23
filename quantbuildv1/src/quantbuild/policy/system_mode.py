"""Central system mode resolution: ``PRODUCTION`` vs ``EDGE_DISCOVERY``.

Mode defaults map to the existing ``filters:`` keys used by ``LiveRunner`` and
the backtest engine so one config switch changes effective policy consistently.
"""

from __future__ import annotations

import warnings
from typing import Any, Dict, List, Tuple

SYSTEM_MODE_PRODUCTION = "PRODUCTION"
SYSTEM_MODE_EDGE_DISCOVERY = "EDGE_DISCOVERY"

FILTER_KEYS = (
    "regime",
    "session",
    "cooldown",
    "news",
    "position_limit",
    "daily_loss",
    "spread",
    "research_raw_first",
    # Backtest-only: SQE pas na align met 1h structure (`_apply_h1_gate`). Runs before regime/session guards.
    "structure_h1_gate",
)

_DEFAULT_PRODUCTION: Dict[str, bool] = {
    "regime": True,
    "session": True,
    "cooldown": True,
    "news": True,
    "position_limit": True,
    "daily_loss": True,
    "spread": True,
    "research_raw_first": False,
    "structure_h1_gate": True,
}

_DEFAULT_EDGE_DISCOVERY: Dict[str, bool] = {
    "regime": False,
    "session": False,
    "cooldown": False,
    "news": False,
    "position_limit": False,
    "daily_loss": True,
    "spread": True,
    "research_raw_first": True,
    "structure_h1_gate": False,
}


def normalize_system_mode(raw: Any) -> str:
    """Return canonical mode string; unknown values warn and map to PRODUCTION."""
    if raw is None:
        return SYSTEM_MODE_PRODUCTION
    if isinstance(raw, str) and not raw.strip():
        return SYSTEM_MODE_PRODUCTION
    s = str(raw).strip().upper().replace("-", "_")
    if s in ("EDGE", "EDGE_DISCOVERY", "DISCOVERY"):
        return SYSTEM_MODE_EDGE_DISCOVERY
    if s in ("PRODUCTION", "PROD", "LIVE"):
        return SYSTEM_MODE_PRODUCTION
    if s == SYSTEM_MODE_EDGE_DISCOVERY:
        return SYSTEM_MODE_EDGE_DISCOVERY
    if s == SYSTEM_MODE_PRODUCTION:
        return SYSTEM_MODE_PRODUCTION
    warnings.warn(
        f"Unknown system_mode {raw!r}; using {SYSTEM_MODE_PRODUCTION}",
        UserWarning,
        stacklevel=2,
    )
    return SYSTEM_MODE_PRODUCTION


def bypassed_filters_vs_production(effective: Dict[str, bool]) -> List[str]:
    """Filters enabled in PRODUCTION defaults but disabled in ``effective`` (e.g. EDGE_DISCOVERY).

    Used for QuantLog ``bypassed_by_mode`` — which suppressions are lifted vs production.
    """
    out: List[str] = []
    for k in FILTER_KEYS:
        if _DEFAULT_PRODUCTION.get(k) and not effective.get(k, True):
            out.append(k)
    return out


def resolve_effective_filters(cfg: Dict[str, Any]) -> Tuple[str, Dict[str, bool]]:
    """Return ``(system_mode, effective_filters)``.

    Starts from mode defaults, then applies explicit ``filters:`` overrides from
    ``cfg`` (same keys as ``FILTER_KEYS``).
    """
    mode = normalize_system_mode(cfg.get("system_mode"))
    base = (
        dict(_DEFAULT_PRODUCTION)
        if mode == SYSTEM_MODE_PRODUCTION
        else dict(_DEFAULT_EDGE_DISCOVERY)
    )
    user = cfg.get("filters") or {}
    if not isinstance(user, dict):
        user = {}
    out: Dict[str, bool] = dict(base)
    for k in FILTER_KEYS:
        if k in user:
            out[k] = bool(user[k])
    return mode, out

