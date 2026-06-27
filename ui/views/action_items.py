"""Ranked, data-driven action items compiled from the deliverables."""
from __future__ import annotations

import sys

import streamlit as st

from ui import data, runners, style

_PRIO_COLOR = {"high": style.ROSE, "medium": style.AMBER, "low": style.SLATE}


def render():
    st.header("Action items")
    st.caption("What to change, ranked by how much of the corpus it touches × how "
               "much it matters. Compiled from the deliverables.")
    marker = data.last_sync_marker()
    df = data.action_items(marker)
    labels = data.label_map(marker)

    if df.empty:
        st.info("No action items yet. Use 'Rebuild scores & insights' on the Run pipeline page.")
        if st.button("▶ Compile action items now"):
            meta = runners.launch([sys.executable, "-m", "skills.corpus.action_items"],
                                  "actionitems")
            st.session_state["run_actionitems"] = meta["run_id"]
            st.rerun()
        return

    cols = st.columns([1, 1, 2])
    src = cols[0].selectbox("Source", ["All"] + sorted(df["source_label"].dropna().unique()))
    prio = cols[1].selectbox("Priority", ["All", "high", "medium", "low"])
    view = df.copy()
    if src != "All":
        view = view[view["source_label"] == src]
    if prio != "All":
        view = view[view["priority"] == prio]

    for _, it in view.iterrows():
        color = _PRIO_COLOR.get(it.get("priority"), style.SLATE)
        stat = it.get("supporting_stat") or {}
        if stat.get("pct"):
            stat_txt = f"{stat['pct']:.0f}% of calls (n={stat.get('n_calls')})"
        elif stat.get("n_calls"):
            stat_txt = f"{stat['n_calls']} calls"
        else:
            stat_txt = ""
        with st.container(border=True):
            top = st.columns([8, 2])
            with top[0]:
                st.markdown(
                    f'{style.badge(str(it.get("priority","")).upper(), color)} '
                    f'<span class="ew-src">{it.get("source_label","")}</span>',
                    unsafe_allow_html=True)
                # full text — no truncation; escape $ so it isn't read as LaTeX
                st.markdown(f"**{style.safe_md(it.get('detail') or it.get('title',''))}**")
            with top[1]:
                if stat_txt:
                    st.metric("Reach", stat_txt.split(" of")[0] if "%" in stat_txt else stat_txt)
            ex = it.get("example_calls") or []
            if len(ex):
                st.caption("Heard on:")
                ecols = st.columns(min(len(ex), 4))
                for i, cid in enumerate(ex[:4]):
                    if ecols[i].button(labels.get(cid, cid), key=f"ai_{it.get('id')}_{cid}",
                                       width='stretch'):
                        st.session_state["selected_call"] = cid
                        st.session_state["_nav"] = "Call detail"
                        st.rerun()
