"""Shared Streamlit UI fragments (Sprint B)."""

from __future__ import annotations

import streamlit as st

from config import events_root, explainer_max_events, health_max_events, table_max_events
from utils.quick_filters import quick_mode_label
from utils.session_state import (
    KEY_DAY,
    KEY_QUICK,
    QUICK_ALL,
    QUICK_ENTER,
    QUICK_ERRORS,
    QUICK_NO_ACTION,
    QUICK_UNKNOWN,
    ensure_session_defaults,
    format_copy_block,
    get_pinned_run_id,
    get_quick_filter_mode,
)


def ensure_day_option(dates: list[str]) -> None:
    ensure_session_defaults(st.session_state)
    if dates and (
        KEY_DAY not in st.session_state
        or st.session_state[KEY_DAY] not in dates
    ):
        st.session_state[KEY_DAY] = dates[-1]


def render_quick_filter_bar() -> None:
    ensure_session_defaults(st.session_state)
    options = [QUICK_ALL, QUICK_ENTER, QUICK_NO_ACTION, QUICK_ERRORS, QUICK_UNKNOWN]
    st.markdown("**Quick filter** (applied first; then detail filters on Explorer)")
    st.radio(
        "Quick filter mode",
        options=options,
        format_func=quick_mode_label,
        horizontal=True,
        key=KEY_QUICK,
        label_visibility="collapsed",
    )
    st.caption(f"Active quick filter: **{quick_mode_label(get_quick_filter_mode(st.session_state))}**")


def render_context_copy_block(
    *,
    day: str,
    root_display: str,
    effective_run: str,
    rows_loaded: int,
    page: str,
) -> None:
    txt = format_copy_block(
        day=day,
        events_root=root_display,
        effective_run=effective_run,
        pinned=get_pinned_run_id(st.session_state),
        quick_mode=quick_mode_label(get_quick_filter_mode(st.session_state)),
        rows_loaded=rows_loaded,
        table_cap=table_max_events(),
        health_cap=health_max_events(),
        explainer_cap=explainer_max_events(),
    )
    with st.expander(f"Context & copy block — {page}", expanded=False):
        st.code(txt, language="text")


def sidebar_events_root_input() -> str:
    root_default = events_root()
    return str(
        st.sidebar.text_input(
            "Events root", value=str(root_default), key="ops_events_root"
        )
    )


def reset_filters_sidebar_button(valid_ids: list[str]) -> None:
    from utils.session_state import reset_filters

    if st.sidebar.button("Reset filters", key="ops_reset_filters"):
        reset_filters(st.session_state, valid_ids=valid_ids)
        st.rerun()
