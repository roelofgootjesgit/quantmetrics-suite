"""Ops Console configuration — read-only paths from environment."""

from __future__ import annotations

import os
from pathlib import Path


def events_root() -> Path:
    """Root directory containing ``YYYY-MM-DD/*.jsonl`` QuantLog shards."""
    env = os.environ.get("QUANTLOG_OPS_EVENTS_ROOT") or os.environ.get(
        "QUANTLOG_EVENTS_ROOT"
    )
    if env:
        return Path(env).expanduser().resolve()
    return Path("data/quantlog_events").resolve()


def max_events_per_load() -> int:
    """Legacy default — used when per-use caps are unset."""
    raw = os.environ.get("QUANTLOG_OPS_MAX_EVENTS", "10000")
    try:
        return max(1, min(int(raw), 100_000))
    except ValueError:
        return 10_000


def _cap_from_env(name: str, fallback: int) -> int:
    raw = os.environ.get(name)
    if raw is None or not str(raw).strip():
        return fallback
    try:
        return max(1, min(int(raw), 100_000))
    except ValueError:
        return fallback


def table_max_events() -> int:
    """Event Explorer, run table on Daily Control, Downloads CSV slice, Decision Breakdown slice."""
    return _cap_from_env("QUANTLOG_OPS_TABLE_MAX_EVENTS", max_events_per_load())


def health_max_events() -> int:
    """Daily Control desk health KPI slice (ratios, errors in cap, unknown %)."""
    return _cap_from_env("QUANTLOG_OPS_HEALTH_MAX_EVENTS", max_events_per_load())


def explainer_max_events() -> int:
    """No-trade explainer regime/timing lines (normalized rows)."""
    return _cap_from_env("QUANTLOG_OPS_EXPLAINER_MAX_EVENTS", max_events_per_load())
