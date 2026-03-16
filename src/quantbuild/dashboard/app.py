"""Streamlit dashboard for Quantbuild E1 — live P&L, positions, news, config."""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def run_dashboard():
    """Launch Streamlit dashboard."""
    try:
        import streamlit as st
    except ImportError:
        print("Dashboard requires streamlit. Run: pip install streamlit")
        sys.exit(1)

    st.set_page_config(page_title="Quantbuild E1 — XAUUSD", page_icon="🥇", layout="wide")
    st.title("🥇 Quantbuild E1 — XAUUSD Trading Dashboard")

    # Sidebar
    st.sidebar.header("Status")
    state_file = ROOT / "data" / "state.json"
    if state_file.exists():
        state = json.loads(state_file.read_text())
        st.sidebar.metric("Open Positions", len(state))
    else:
        st.sidebar.metric("Open Positions", 0)

    st.sidebar.markdown("---")
    st.sidebar.info(f"Last refresh: {datetime.now(timezone.utc).strftime('%H:%M:%S UTC')}")

    # Main tabs
    tab_pnl, tab_positions, tab_news, tab_config = st.tabs(["P&L", "Positions", "News", "Config"])

    with tab_pnl:
        st.subheader("Equity Curve")
        metrics_file = ROOT / "reports" / "latest" / "metrics.json"
        if metrics_file.exists():
            metrics = json.loads(metrics_file.read_text())
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Net PnL", f"${metrics.get('net_pnl', 0):.2f}")
            col2.metric("Profit Factor", f"{metrics.get('profit_factor', 0):.2f}")
            col3.metric("Win Rate", f"{metrics.get('win_rate', 0):.1f}%")
            col4.metric("Max DD", f"{metrics.get('max_drawdown', 0):.2f}R")
        else:
            st.info("No metrics available. Run a backtest first.")

    with tab_positions:
        st.subheader("Open Positions")
        if state_file.exists() and state:
            for tid, pos in state.items():
                with st.expander(f"{pos['direction']} @ {pos['entry_price']:.2f}"):
                    st.json(pos)
        else:
            st.info("No open positions.")

    with tab_news:
        st.subheader("Recent News Events")
        news_cache = ROOT / "data" / "news_cache" / "latest_events.json"
        if news_cache.exists():
            events = json.loads(news_cache.read_text())
            for ev in events[:20]:
                st.markdown(f"**[{ev.get('source_name', '?')}]** {ev.get('headline', '')}")
                if ev.get("topic_hints"):
                    st.caption(f"Topics: {', '.join(ev['topic_hints'])}")
        else:
            st.info("No news events cached yet. Enable the news layer and run live mode.")

    with tab_config:
        st.subheader("Current Configuration")
        config_file = ROOT / "configs" / "xauusd.yaml"
        if config_file.exists():
            st.code(config_file.read_text(), language="yaml")
        else:
            st.warning("Config file not found.")


if __name__ == "__main__":
    run_dashboard()
