"""Daily snapshot — runs, KPIs, health, no-trade explainer (Sprint A/B)."""

from __future__ import annotations

import sys
from pathlib import Path

_OPS = Path(__file__).resolve().parents[1]
if str(_OPS) not in sys.path:
    sys.path.insert(0, str(_OPS))

import streamlit as st

from config import (
    explainer_max_events,
    health_max_events,
    table_max_events,
)
from page_fragments import (
    ensure_day_option,
    render_context_copy_block,
    sidebar_events_root_input,
)
from services.health import compute_signal_ratios, count_unknown_label_events
from services.no_trade_explainer import build_no_trade_lines
from services.summarizer import dominant_reason, summarize
from streamlit_cache import (
    cached_index_day,
    cached_list_date_dirs,
    cached_load_bounded,
    cached_scan_day,
)
from utils.session_state import (
    ALL_RUNS,
    KEY_DAY,
    KEY_RUN,
    get_pinned_run_id,
    get_selected_run_id,
    sanitize_run_selection,
    set_pinned_run_id,
    valid_run_ids_for_day,
)

_ss = st.session_state

st.title("Daily Control")

root_str = sidebar_events_root_input()
root = Path(root_str).expanduser()

dates = cached_list_date_dirs(str(root))
if not dates:
    st.warning(
        f"No ``YYYY-MM-DD`` directories under {root}. Set **QUANTLOG_OPS_EVENTS_ROOT**."
    )
    st.stop()

ensure_day_option(dates)
st.sidebar.selectbox("Day", dates, key=KEY_DAY)
sel = str(st.session_state[KEY_DAY])

table_cap = table_max_events()
health_cap = health_max_events()
explainer_cap = explainer_max_events()

r_s = str(root)
idx = cached_index_day(r_s, sel)
run_ids = valid_run_ids_for_day(idx)
sanitize_run_selection(_ss, run_ids)

run_opts = [ALL_RUNS] + run_ids
if _ss.get(KEY_RUN) not in run_opts:
    _ss[KEY_RUN] = ALL_RUNS

st.sidebar.selectbox("Run focus (shared across pages)", run_opts, key=KEY_RUN)
rp1, rp2 = st.sidebar.columns(2)
with rp1:
    if st.button("Pin current run", key="ops_pin_run_dc"):
        cur = get_selected_run_id(_ss)
        if cur != ALL_RUNS:
            set_pinned_run_id(_ss, cur)
            st.success(f"Pinned **{cur}** for this day.")
with rp2:
    if st.button("Unpin", key="ops_unpin_dc"):
        set_pinned_run_id(_ss, None)

st.sidebar.caption(
    f"**Pinned:** {get_pinned_run_id(_ss) or '—'}  \n"
    "Other pages use **Run focus** from session state. Pin is a label for desk context."
)

scan = cached_scan_day(r_s, sel)

rows_health = cached_load_bounded(r_s, sel, "__all__", cap=health_cap)
rows_explainer = cached_load_bounded(r_s, sel, "__all__", cap=explainer_cap)
cap_hit_explainer = len(rows_explainer) >= explainer_cap

s_health = summarize(rows_health)
ratios = compute_signal_ratios(rows_health)
unk_n, tot_labels = count_unknown_label_events(rows_health)
pct_unknown = 100.0 * unk_n / max(tot_labels, 1)

st.info(
    f"**Context** — Day `{sel}` · Run focus `{get_selected_run_id(_ss)}` · "
    f"Pinned `{get_pinned_run_id(_ss) or '—'}`  \n"
    "_Next: open **Decision Breakdown** or **Event Explorer** — same day/run carry over._"
)

st.markdown("### Desk health")
st.caption(
    f"Health metrics based on first **{health_cap}** normalized events "
    f"(`QUANTLOG_OPS_HEALTH_MAX_EVENTS`)."
)
h1, h2, h3, h4, h5, h6 = st.columns(6)
h1.metric("Last event (full JSONL scan)", scan.get("last_timestamp_utc") or "—")
h2.metric("Active runs", len(idx.get("runs", [])))
h3.metric("Parse fallback %", f"{scan.get('pct_parse_fallback', 0):.2f}")
h4.metric("Errors (health slice)", s_health.get("errors", 0))
h5.metric("eval → trade_action", f"{ratios['ratio_eval_to_trade_action']:.2f}")
h6.metric("eval → ENTER", f"{ratios['ratio_eval_to_enter']:.3f}")
st.caption(
    f"Fields labelled **unknown** in parser (health slice): **{pct_unknown:.1f}%** "
    f"({unk_n}/{tot_labels} rows). "
    f"Parse fallback = JSON lines that failed ``json.loads``."
)

rows_table: list[dict] = []
grand_events = 0
grand_signals = 0
grand_entries = 0
grand_noaction = 0
grand_errors = 0
all_reasons: dict[str, int] = {}

for run in idx.get("runs", []):
    rid = run["run_id"]
    scope = "__unknown__" if rid == "(unknown_run)" else rid
    loaded = cached_load_bounded(r_s, sel, scope, cap=table_cap)

    s = summarize(loaded)
    grand_events += s["total_events"]
    grand_signals += s["signals"]
    grand_entries += s["entries"]
    grand_noaction += s["no_action"]
    grand_errors += s["errors"]
    for k, v in (s.get("by_reason") or {}).items():
        all_reasons[k] = all_reasons.get(k, 0) + v

    rows_table.append(
        {
            "Run ID": rid,
            "Events": s["total_events"],
            "Signals": s["signals"],
            "Entries": s["entries"],
            "No Action": s["no_action"],
            "Errors": s["errors"],
            "Top reason": dominant_reason(s) or "—",
            "Files": len(run.get("files", [])),
        }
    )

s_explainer = summarize(rows_explainer)
lines = build_no_trade_lines(
    summary=s_explainer,
    rows=rows_explainer,
    scan=scan,
    cap_hit=cap_hit_explainer,
    merged_reason_counts=all_reasons,
    total_entries=grand_entries,
)
with st.expander("No-trade summary", expanded=True):
    st.caption(
        f"No-trade explainer uses the first **{explainer_cap}** normalized events "
        f"(`QUANTLOG_OPS_EXPLAINER_MAX_EVENTS`)."
    )
    for ln in lines:
        st.markdown(f"- {ln}")

st.subheader(f"Day {sel}")
k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Runs", len(rows_table))
k2.metric("Events (sum per run)", grand_events)
k3.metric("Signals (sum)", grand_signals)
k4.metric("Entries (trade_executed)", grand_entries)
dom = max(all_reasons.items(), key=lambda kv: kv[1])[0] if all_reasons else "—"
k5.metric("Dominant reason (merged)", dom)

st.caption(
    f"Run table: **{table_cap}** events per run (`QUANTLOG_OPS_TABLE_MAX_EVENTS`). "
    "Health and explainer caps are independent."
)

st.dataframe(rows_table, use_container_width=True, hide_index=True)

render_context_copy_block(
    day=sel,
    root_display=str(root.resolve()),
    effective_run=get_selected_run_id(_ss),
    rows_loaded=grand_events,
    page="Daily Control",
)

if st.sidebar.checkbox("Show run file list"):
    st.json(idx)
