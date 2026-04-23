"""Bronze layer: envelope + flatten payload columns (no interpretation)."""

from __future__ import annotations

import json
from typing import Any

import pandas as pd


def _cell_value(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, (list, dict)):
        return json.dumps(value, sort_keys=True, ensure_ascii=False)
    return str(value)


def flatten_event(event: dict[str, Any]) -> dict[str, Any]:
    """One event row: envelope keys + payload_* columns."""
    row: dict[str, Any] = {}
    payload = event.get("payload")
    for key, val in event.items():
        if key == "payload":
            continue
        row[key] = val
    if isinstance(payload, dict):
        for pk, pv in payload.items():
            row[f"payload_{pk}"] = _cell_value(pv)
    elif payload is not None:
        row["payload_non_object"] = _cell_value(payload)
    return row


def events_to_dataframe(events: list[dict[str, Any]]) -> pd.DataFrame:
    if not events:
        return pd.DataFrame()
    rows = [flatten_event(ev) for ev in events]
    df = pd.DataFrame(rows)
    # Stable column order: envelope-like first if present
    preferred = [
        "event_id",
        "event_type",
        "event_version",
        "timestamp_utc",
        "ingested_at_utc",
        "trace_id",
        "run_id",
        "session_id",
        "source_seq",
        "severity",
    ]
    cols = list(df.columns)
    ordered = [c for c in preferred if c in cols]
    ordered.extend(sorted(c for c in cols if c not in ordered))
    return df[ordered]
