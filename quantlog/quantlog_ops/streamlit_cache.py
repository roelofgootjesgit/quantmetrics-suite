"""Central @st.cache_data entry points — use from all pages (Sprint A)."""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from services.day_scan import scan_day_jsonl_stats
from services.event_loader import load_day_events
from services.file_indexer import index_day, list_date_dirs


@st.cache_data(ttl=300, max_entries=32, show_spinner=False)
def cached_list_date_dirs(root: str) -> list[str]:
    return list_date_dirs(Path(root).expanduser())


@st.cache_data(ttl=300, max_entries=128, show_spinner=False)
def cached_index_day(root: str, day: str) -> dict:
    return index_day(Path(root).expanduser() / day)


@st.cache_data(ttl=300, max_entries=64, show_spinner=False)
def cached_scan_day(root: str, day: str) -> dict:
    """Full JSONL scan: parse failures, first/last timestamps."""
    return scan_day_jsonl_stats(Path(root).expanduser() / day)


@st.cache_data(ttl=300, max_entries=512, show_spinner=False)
def cached_load_bounded(
    root: str,
    day: str,
    scope: str,
    *,
    cap: int,
) -> list[dict]:
    """
    Bounded normalized load. Pass the cap for your use case (table / health / explainer).

    ``scope``:

    - ``__all__`` — whole day directory, merge order
    - ``__unknown__`` — events with empty ``run_id``
    - else — literal ``run_id``
    """
    day_path = Path(root).expanduser() / day
    if scope == "__all__":
        return load_day_events(day_path, run_id=None, max_events=cap)
    if scope == "__unknown__":
        rows = load_day_events(day_path, run_id=None, max_events=cap)
        return [x for x in rows if not str(x.get("run_id") or "").strip()]
    return load_day_events(day_path, run_id=scope, max_events=cap)
