"""Stable QuantLog run/session identifiers shared by live_runner and backtest."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


def resolve_quantlog_run_id(ql_cfg: dict[str, Any]) -> str:
    """Stable non-empty run_id: explicit config wins, else env, else timestamp default.

    YAML often sets ``run_id: ""`` intending "auto"; ``dict.get`` would otherwise yield
    an empty string and skip the default — that breaks QuantLog correlatie (P1).
    """
    raw = ql_cfg.get("run_id")
    if raw is not None:
        s = str(raw).strip()
        if s:
            return s
    for env_key in ("QUANTBUILD_RUN_ID", "INVOCATION_ID"):
        v = os.environ.get(env_key, "").strip()
        if v:
            return v
    # Sub-second suffix so parallel backtests (same UTC second) never share one run_id.
    return f"qb_run_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_{uuid4().hex[:8]}"


def resolve_quantlog_session_id(ql_cfg: dict[str, Any]) -> str:
    """Non-empty session_id: explicit config, else QUANTBUILD_SESSION_ID, else random."""
    raw = ql_cfg.get("session_id")
    if raw is not None:
        s = str(raw).strip()
        if s:
            return s
    env_sid = os.environ.get("QUANTBUILD_SESSION_ID", "").strip()
    if env_sid:
        return env_sid
    return f"qb_session_{uuid4().hex[:10]}"
