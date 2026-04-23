"""QuantLog Ops Console — Streamlit entry (handbook v0.1)."""

from __future__ import annotations

import sys
from pathlib import Path

_OPS = Path(__file__).resolve().parent
if str(_OPS) not in sys.path:
    sys.path.insert(0, str(_OPS))

import streamlit as st

st.set_page_config(page_title="QuantLog Ops Console", layout="wide")
st.title("QuantLog Ops Console")
st.caption("Read-only operator layer on QuantLog JSONL — no trading actions.")
st.markdown(
    "Navigate via the sidebar: **Daily Control** (snapshot), **Decision Breakdown**, "
    "**Event Explorer**, **Downloads**."
)
