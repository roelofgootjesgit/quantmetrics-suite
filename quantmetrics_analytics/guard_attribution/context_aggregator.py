"""Aggregate block counts by guard / regime / session / setup."""

from __future__ import annotations

from typing import Any

import pandas as pd


def aggregate_guard_context(blocks: pd.DataFrame) -> dict[str, Any]:
    """Return nested summary for JSON / report (passive attribution)."""
    if blocks.empty:
        return {
            "total_blocks": 0,
            "by_guard": {},
            "by_regime": {},
            "by_session": {},
            "by_setup_type": {},
        }
    total = int(len(blocks))
    by_guard = blocks.groupby("guard_name").size().to_dict()
    by_regime = (
        blocks.groupby(blocks["regime"].fillna("unknown")).size().to_dict() if "regime" in blocks.columns else {}
    )
    by_session = (
        blocks.groupby(blocks["session"].fillna("unknown")).size().to_dict() if "session" in blocks.columns else {}
    )
    by_setup = (
        blocks.groupby(blocks["setup_type"].fillna("unknown")).size().to_dict()
        if "setup_type" in blocks.columns
        else {}
    )

    share_guard = {str(k): float(v) / total for k, v in by_guard.items()}
    return {
        "total_blocks": total,
        "by_guard": {str(k): int(v) for k, v in by_guard.items()},
        "share_by_guard": share_guard,
        "by_regime": {str(k): int(v) for k, v in by_regime.items()},
        "by_session": {str(k): int(v) for k, v in by_session.items()},
        "by_setup_type": {str(k): int(v) for k, v in by_setup.items()},
    }
