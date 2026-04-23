"""Filter and inspect raw events — Sprint B sticky state & quick filters."""

from __future__ import annotations

import json
import sys
from pathlib import Path

_OPS = Path(__file__).resolve().parents[1]
if str(_OPS) not in sys.path:
    sys.path.insert(0, str(_OPS))

import pandas as pd
import streamlit as st

from config import table_max_events
from page_fragments import (
    ensure_day_option,
    render_context_copy_block,
    render_quick_filter_bar,
    reset_filters_sidebar_button,
    sidebar_events_root_input,
)
from streamlit_cache import cached_index_day, cached_list_date_dirs, cached_load_bounded
from utils.filters import apply_filters
from utils.quick_filters import apply_quick_filter, quick_mode_label
from utils.session_state import (
    ALL_RUNS,
    KEY_DAY,
    KEY_DECISION,
    KEY_EVENT_TYPE,
    KEY_REGIME,
    KEY_RUN,
    KEY_SYMBOL,
    ensure_session_defaults,
    get_quick_filter_mode,
    get_selected_run_id,
    sanitize_run_selection,
    scope_from_run_pick,
    valid_run_ids_for_day,
)

st.title("Event Explorer")

_ss = st.session_state
ensure_session_defaults(_ss)

root_str = sidebar_events_root_input()
root = Path(root_str).expanduser()

dates = cached_list_date_dirs(str(root))
if not dates:
    st.warning("No date directories found.")
    st.stop()

ensure_day_option(dates)
st.sidebar.selectbox("Day", dates, key=KEY_DAY)
sel = str(_ss[KEY_DAY])

r_s = str(root)
idx = cached_index_day(r_s, sel)
run_ids = valid_run_ids_for_day(idx)
sanitize_run_selection(_ss, run_ids)
run_opts = [ALL_RUNS] + run_ids
if _ss.get(KEY_RUN) not in run_opts:
    _ss[KEY_RUN] = ALL_RUNS

st.sidebar.selectbox("Run / scope", run_opts, key=KEY_RUN)

st.sidebar.markdown("---")
st.sidebar.caption("Detail filters (substring match, **after** quick filter)")
fe = st.sidebar.text_input("event_type contains", key=KEY_EVENT_TYPE)
fd = st.sidebar.text_input("decision contains", key=KEY_DECISION)
fs = st.sidebar.text_input("symbol contains", key=KEY_SYMBOL)
fr = st.sidebar.text_input("regime contains", key=KEY_REGIME)
reset_filters_sidebar_button(run_ids)

table_cap = table_max_events()
run_pick = get_selected_run_id(_ss)
scope = scope_from_run_pick(run_pick)

render_quick_filter_bar()
mode = get_quick_filter_mode(_ss)

rows = cached_load_bounded(r_s, sel, scope, cap=table_cap)
after_quick = apply_quick_filter(rows, mode)

st.caption(
    f"Explorer limited to first **{table_cap}** normalized events "
    f"(`QUANTLOG_OPS_TABLE_MAX_EVENTS`). **Quick filter:** {quick_mode_label(mode)} — "
    "applied before detail filters."
)

st.info(
    f"**Context** — Day `{sel}` · Run `{run_pick}` · Quick **{quick_mode_label(mode)}**"
)

filtered = apply_filters(
    after_quick,
    event_type=fe or None,
    decision=fd or None,
    symbol=fs or None,
    regime=fr or None,
)

display_keys = [
    "timestamp_utc",
    "run_id",
    "event_type",
    "symbol",
    "session",
    "regime",
    "decision",
    "reason_code",
    "confidence",
    "source_system",
    "order_ref",
    "_source_file",
    "_line",
]

flat = []
for r in filtered:
    line = {k: r.get(k) for k in display_keys if k in r}
    flat.append(line)

st.metric("Rows shown (after quick + detail filters)", len(flat))
if not flat:
    st.warning("No rows match. Try **Reset filters** or change quick filter.")
    render_context_copy_block(
        day=sel,
        root_display=str(root.resolve()),
        effective_run=run_pick,
        rows_loaded=0,
        page="Event Explorer",
    )
    st.stop()

df = pd.DataFrame(flat)
st.dataframe(df, use_container_width=True, hide_index=True)


def _row_label(i: int) -> str:
    r = flat[i]
    return f"{r.get('timestamp_utc','')} | {r.get('event_type','')} | {r.get('run_id','')}"


pick = st.selectbox(
    "Inspect raw JSON",
    options=range(len(filtered)),
    format_func=_row_label,
)
raw = filtered[pick].get("_raw")
st.subheader("Raw JSON")
st.code(json.dumps(raw, indent=2, ensure_ascii=False), language="json")

render_context_copy_block(
    day=sel,
    root_display=str(root.resolve()),
    effective_run=run_pick,
    rows_loaded=len(flat),
    page="Event Explorer",
)
