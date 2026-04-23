"""Why no trades — reasons, regimes, no-trade explainer (Sprint A/B)."""

from __future__ import annotations

import sys
from pathlib import Path

_OPS = Path(__file__).resolve().parents[1]
if str(_OPS) not in sys.path:
    sys.path.insert(0, str(_OPS))

import pandas as pd
import streamlit as st

from config import explainer_max_events, table_max_events
from page_fragments import (
    ensure_day_option,
    render_context_copy_block,
    render_quick_filter_bar,
    reset_filters_sidebar_button,
    sidebar_events_root_input,
)
from services.no_trade_explainer import build_no_trade_lines
from services.summarizer import summarize
from streamlit_cache import (
    cached_index_day,
    cached_list_date_dirs,
    cached_load_bounded,
    cached_scan_day,
)
from utils.quick_filters import apply_quick_filter, quick_mode_label
from utils.session_state import (
    ALL_RUNS,
    KEY_DAY,
    KEY_RUN,
    ensure_session_defaults,
    get_quick_filter_mode,
    get_selected_run_id,
    sanitize_run_selection,
    scope_from_run_pick,
    valid_run_ids_for_day,
)

st.title("Decision Breakdown")

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
reset_filters_sidebar_button(run_ids)

table_cap = table_max_events()
explainer_cap = explainer_max_events()

run_pick = get_selected_run_id(_ss)
scope = scope_from_run_pick(run_pick)

render_quick_filter_bar()
mode = get_quick_filter_mode(_ss)

rows = cached_load_bounded(r_s, sel, scope, cap=table_cap)
rows_expl = cached_load_bounded(r_s, sel, scope, cap=explainer_cap)

qf_rows = apply_quick_filter(rows, mode)
qf_expl = apply_quick_filter(rows_expl, mode)
cap_hit_expl = len(rows_expl) >= explainer_cap

scan = cached_scan_day(r_s, sel)
s = summarize(qf_rows)
s_expl = summarize(qf_expl)
by_reason = s.get("by_reason") or {}
by_regime = s.get("by_regime") or {}

st.info(
    f"**Context** — Day `{sel}` · Run `{run_pick}` · Quick **{quick_mode_label(mode)}** · "
    f"Charts: **{len(qf_rows)}** rows (from **{len(rows)}** loaded / cap **{table_cap}**)."
)

st.caption(
    f"Tables use quick-filtered rows. Loaded slice: **{len(rows)}** events "
    f"(cap **{table_cap}**). Quick filter: **{quick_mode_label(mode)}**."
)

st.subheader("Summary")
c1, c2, c3 = st.columns(3)
c1.metric("NO_ACTION rows", s.get("no_action", 0))
c2.metric("Signals (eval+detect)", s.get("signals", 0))
c3.metric("Entries (trade_executed)", s.get("entries", 0))

st.markdown("### reason_code / blockers (NO_ACTION + signal_filtered)")
if by_reason:
    total = sum(by_reason.values())
    pct = {k: (100.0 * v / total) for k, v in by_reason.items()}
    df_r = pd.DataFrame(
        [{"reason": k, "count": by_reason[k], "pct": round(pct[k], 1)} for k in by_reason]
    )
    df_r = df_r.sort_values("count", ascending=False)
    st.dataframe(df_r, use_container_width=True, hide_index=True)
    st.bar_chart(df_r.set_index("reason")["count"])
else:
    st.info("No aggregated reasons in this slice (or no NO_ACTION / filter rows).")

st.markdown("### Regime distribution (from NO_ACTION + signal rows)")
if by_regime:
    df_g = pd.DataFrame(
        [{"regime": k, "count": v} for k, v in by_regime.items()]
    ).sort_values("count", ascending=False)
    st.dataframe(df_g, use_container_width=True, hide_index=True)
    st.bar_chart(df_g.set_index("regime")["count"])
else:
    st.info("No regime fields in this slice.")

lines = build_no_trade_lines(
    summary=s_expl,
    rows=qf_expl,
    scan=scan,
    cap_hit=cap_hit_expl,
    merged_reason_counts=by_reason,
    total_entries=s.get("entries", 0),
)
with st.expander("No-trade summary", expanded=True):
    st.caption(
        f"No-trade explainer uses first **{explainer_cap}** loaded events "
        f"(`QUANTLOG_OPS_EXPLAINER_MAX_EVENTS`), then quick filter "
        f"**{quick_mode_label(mode)}** → **{len(qf_expl)}** rows."
    )
    for ln in lines:
        st.markdown(f"- {ln}")

render_context_copy_block(
    day=sel,
    root_display=str(root.resolve()),
    effective_run=run_pick,
    rows_loaded=len(qf_rows),
    page="Decision Breakdown",
)
