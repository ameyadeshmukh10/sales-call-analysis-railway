"""Filterable explorer over all calls — human labels, readable columns."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from ui import data, style


def render():
    st.header("Calls")
    marker = data.last_sync_marker()
    df = data.calls_table(marker)
    if df.empty:
        st.info("No calls yet. Run ingest from the Run pipeline page.")
        return

    f = st.columns(5)
    reps = ["All"] + sorted(x for x in df["rep"].dropna().unique())
    rep = f[0].selectbox("Rep", reps)
    personas = ["All"] + sorted(x for x in df["persona"].dropna().unique())
    persona = f[1].selectbox("Persona", personas)
    outcomes = ["All"] + sorted(df["deal_status"].dropna().unique())
    outcome = f[2].selectbox("Deal outcome", outcomes)
    tiers = ["All"] + sorted(x for x in df["icp_tier"].dropna().unique())
    tier = f[3].selectbox("ICP tier", tiers)
    only_analyzed = f[4].checkbox("Analyzed only", value=False)

    view = df.copy()
    if rep != "All":
        view = view[view["rep"] == rep]
    if persona != "All":
        view = view[view["persona"] == persona]
    if outcome != "All":
        view = view[view["deal_status"] == outcome]
    if tier != "All":
        view = view[view["icp_tier"] == tier]
    if only_analyzed:
        view = view[view["analyzed"]]

    st.caption(f"{len(view)} of {len(df)} calls — click a row's Open button below to dive in.")

    view = view.copy()
    view["company"] = view["company"].fillna("(no account)")
    show = view[["company", "hs_timestamp", "rep", "persona", "icp_tier",
                 "discovery", "n_objections", "next_step_strength", "composite",
                 "deal_status"]].copy()
    show = show.rename(columns={
        "company": "Account", "hs_timestamp": "Date", "rep": "Rep", "persona": "Persona",
        "icp_tier": "ICP", "discovery": "Discovery", "n_objections": "Objections",
        "next_step_strength": "Next step", "composite": "Score", "deal_status": "Outcome"})
    st.dataframe(
        show, width='stretch', hide_index=True,
        column_config={
            "Date": st.column_config.DatetimeColumn("Date", format="MMM D"),
            "Discovery": st.column_config.ProgressColumn("Discovery", min_value=0, max_value=100, format="%d"),
            "Score": st.column_config.NumberColumn("Score", format="%.0f"),
            "Next step": st.column_config.NumberColumn("Next step", help="0–3, strength of the agreed next step"),
        })

    st.divider()
    labels = dict(zip(view["label"], view["call_id"]))
    pick = st.selectbox("Open a call →", ["—"] + list(labels.keys()))
    if pick != "—":
        st.session_state["selected_call"] = labels[pick]
        st.session_state["_nav"] = "Call detail"
        st.rerun()
