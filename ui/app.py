"""EverWorker — Sales Call Intelligence dashboard.

Run:  streamlit run ui/app.py   (from the repo root)

Reads the SQLite store + outputs/ (never re-analyzes on its own) and triggers the
pipeline via ui/runners.py. Dark + emerald EverWorker theme.
"""
from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

# ensure repo root on path so `pipeline` / `skills` import when run via streamlit
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Ensure the SQLite schema exists so the dashboard boots on a fresh volume (empty
# DB, before any ingest has run). Idempotent — CREATE TABLE IF NOT EXISTS.
from pipeline import store  # noqa: E402
store.init_db()

from ui import style  # noqa: E402
from ui.views import (  # noqa: E402
    action_items as p_action,
    call_detail as p_detail,
    calls as p_calls,
    insights as p_insights,
    objections as p_obj,
    overview_run as p_run,
    scripts as p_scripts,
)

st.set_page_config(page_title="EverWorker · Call Intelligence",
                   page_icon="🟢", layout="wide")
st.markdown(style.GLOBAL_CSS, unsafe_allow_html=True)

# Insight-first: takeaways land first; operator controls last.
PAGES = {
    "Takeaways": p_insights,
    "Objections": p_obj,
    "Scripts": p_scripts,
    "Action items": p_action,
    "Calls": p_calls,
    "Call detail": p_detail,
    "Run pipeline": p_run,
}

with st.sidebar:
    st.markdown("### 🟢 EverWorker")
    st.caption("Sales Call Intelligence")
    default = st.session_state.get("_nav", "Takeaways")
    choice = st.radio("Navigate", list(PAGES.keys()),
                      index=list(PAGES.keys()).index(default) if default in PAGES else 0,
                      label_visibility="collapsed")
    st.session_state["_nav"] = choice
    st.divider()
    st.caption("Reads your local call store. Runs the pipeline on demand.")

PAGES[choice].render()
