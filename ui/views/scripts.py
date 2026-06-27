"""Recommended scripts — rep-facing, word-for-word talk tracks derived from the
corpus. Readable + copy-ready, versioned like every other deliverable."""
from __future__ import annotations

import streamlit as st

from ui import data, style


def _render_one(marker: str, label: str, deliverable: str):
    versions = data.list_deliverable_versions(marker, deliverable)
    if not versions:
        st.info(f"**{label}** hasn't been generated yet. Run analysis (or the "
                f"{deliverable} agent) to create it.")
        return
    cols = st.columns([4, 1])
    cols[0].subheader(label)
    v = cols[1].selectbox("Version", versions, index=len(versions) - 1,
                          key=f"sv_{deliverable}", label_visibility="collapsed")
    dd = data.read_deliverable(marker, deliverable, v)
    if dd.get("diff_md"):
        with st.expander("What changed vs the prior version"):
            st.markdown(style.safe_md(dd["diff_md"]))
    with st.container(border=True):
        st.markdown(style.safe_md(dd.get("md", "")))
    with st.expander("📋 Copy the raw script"):
        st.code(dd.get("md", ""), language="markdown")


def render():
    st.markdown(
        '<div class="ew-hero"><h1>Recommended scripts</h1>'
        '<p>Word-for-word talk tracks built from the corpus — say the pricing right, '
        'run discovery, and structure the call. Derived from 72 analyzed calls; '
        'directional, not gospel.</p></div>', unsafe_allow_html=True)

    marker = data.last_sync_marker()
    items = list(data.SCRIPTS.items())
    if not any(data.list_deliverable_versions(marker, d) for _, d in items):
        st.info("No scripts generated yet. They're produced by the pricing-script / "
                "discovery-script / sequence-script agents (run analysis to create them).")
        return

    tabs = st.tabs([lbl for lbl, _ in items])
    for tab, (lbl, deliverable) in zip(tabs, items):
        with tab:
            _render_one(marker, lbl, deliverable)
