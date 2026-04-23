"""One-click exports — no SSH (handbook §8.4, Sprint B context)."""

from __future__ import annotations

import sys
from pathlib import Path

_OPS = Path(__file__).resolve().parents[1]
if str(_OPS) not in sys.path:
    sys.path.insert(0, str(_OPS))

import streamlit as st

from config import table_max_events
from page_fragments import ensure_day_option, sidebar_events_root_input
from services.exporter import (
    jsonl_shard_timestamp_bounds,
    normalized_export_time_bounds,
    normalized_rows_csv,
    read_jsonl_text,
    zip_day_directory,
    zip_run_files,
)
from streamlit_cache import cached_index_day, cached_list_date_dirs, cached_load_bounded
from utils.quick_filters import quick_mode_label
from utils.session_state import (
    ALL_RUNS,
    KEY_DAY,
    KEY_RUN,
    ensure_session_defaults,
    get_quick_filter_mode,
    get_selected_run_id,
    sanitize_run_selection,
    valid_run_ids_for_day,
)

st.title("Downloads")

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
day_path = root / sel
r_s = str(root)

idx = cached_index_day(r_s, sel)
run_ids = valid_run_ids_for_day(idx)
sanitize_run_selection(_ss, run_ids)
run_opts = [ALL_RUNS] + run_ids
if _ss.get(KEY_RUN) not in run_opts:
    _ss[KEY_RUN] = ALL_RUNS

st.sidebar.selectbox("Run focus (zip scope)", run_opts, key=KEY_RUN)

run_pick = get_selected_run_id(_ss)
run_pick_zip = run_pick if run_pick != ALL_RUNS else run_ids[0] if run_ids else ""

st.info(
    f"**Context** — Day `{sel}` · Run `{run_pick}` · Quick filter "
    f"_(Explorer/Breakdown)_: **{quick_mode_label(get_quick_filter_mode(_ss))}**"
)

st.caption(
    "Day/run mirror session state from **Daily Control** / **Explorer** / **Decision Breakdown**. "
    "Zip buttons follow **run focus** when a concrete run is selected."
)

col1, col2 = st.columns(2)

with col1:
    zday = zip_day_directory(day_path)
    st.download_button(
        label="Download day (all JSONL, zip)",
        data=zday,
        file_name=f"quantlog_{sel}.zip",
        mime="application/zip",
    )

with col2:
    paths: list[Path] = []
    if run_pick_zip:
        for r in idx.get("runs", []):
            if r["run_id"] == run_pick_zip:
                paths = [Path(p) for p in r.get("files", [])]
                break
    if paths:
        zrun = zip_run_files(paths)
        st.download_button(
            label=f"Download run `{run_pick_zip}` (zip)",
            data=zrun,
            file_name=f"quantlog_{sel}_{run_pick_zip}.zip",
            mime="application/zip",
        )
    else:
        st.caption("Choose a concrete run in the sidebar for run-scoped zip, or use day zip.")

st.markdown("---")
st.subheader("Raw JSONL (single shard)")

shard_names: list[str] = []
shard_paths: list[Path] = []
for r in idx.get("runs", []):
    for fp in r.get("files", []):
        p = Path(fp)
        if p.is_file():
            shard_paths.append(p)
            shard_names.append(p.name)
seen: set[str] = set()
opts: list[tuple[str, Path]] = []
for name, p in zip(shard_names, shard_paths):
    key = str(p)
    if key not in seen:
        seen.add(key)
        opts.append((name, p))

if opts:
    labels = [f"{n} — {p}" for n, p in opts]
    choice = st.selectbox("Shard", options=range(len(opts)), format_func=lambda i: labels[i])
    shard_path = opts[choice][1]
    t_shard_lo, t_shard_hi = jsonl_shard_timestamp_bounds(shard_path)
    if t_shard_lo and t_shard_hi:
        st.caption(
            f"**Session folder (UTC date):** `{sel}` · "
            f"**Events in this shard (UTC):** `{t_shard_lo}` → `{t_shard_hi}`"
        )
    else:
        st.caption(
            f"**Session folder (UTC date):** `{sel}` · "
            "**Events in this shard:** no parsable `timestamp_utc` lines found."
        )
    txt = read_jsonl_text([shard_path])
    st.download_button(
        label="Download this JSONL",
        data=txt,
        file_name=opts[choice][1].name,
        mime="application/jsonl",
    )

st.markdown("---")
st.subheader("Normalized summary CSV")

table_cap = table_max_events()
rows = cached_load_bounded(r_s, sel, "__all__", cap=table_cap)
csv_text = normalized_rows_csv(rows)
exp_lo, exp_hi = normalized_export_time_bounds(rows)
csv_cap = (
    f"CSV uses session **day** `{sel}`, scope **__all__**, first **{table_cap}** events "
    f"(`QUANTLOG_OPS_TABLE_MAX_EVENTS`). "
)
if exp_lo and exp_hi:
    csv_cap += (
        f"**Export time window (UTC):** `{exp_lo}` → `{exp_hi}` "
        f"({len(rows)} normalized rows). "
    )
else:
    csv_cap += "**Export time window:** no rows with `timestamp_utc`. "
csv_cap += f"Run focus `{run_pick}` does not slice CSV."
st.caption(csv_cap)
st.download_button(
    label=f"Download normalized CSV (cap {table_cap} events)",
    data=csv_text,
    file_name=f"quantlog_normalized_{sel}.csv",
    mime="text/csv",
)
