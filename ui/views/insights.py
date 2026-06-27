"""Takeaways — the insight-first landing. Plain-language headlines, then the
supporting charts (each with a one-line 'what this means'), then the deliverables."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from ui import charts, data, style


def _stat(card) -> str:
    if card.get("pct") is not None:
        return f"{card['pct']:.0f}%"
    if card.get("n_calls") is not None:
        return f"{card['n_calls']}"
    return "—"


def render():
    marker = data.last_sync_marker()
    k = data.overview_kpis(marker)

    st.markdown(
        '<div class="ew-hero"><h1>What the calls are telling us</h1>'
        f'<p>{k["n_calls"]} recorded calls · {k["pct_analyzed"]:.0f}% analyzed · '
        '2 reps. The biggest patterns, in plain language.</p></div>',
        unsafe_allow_html=True)

    cards = data.headlines(marker)
    if not cards:
        st.info("No analysis yet. Go to **Run pipeline** to analyze your calls.")
        return

    st.caption("⚠️ Directional, not statistical — 77 calls (72 analyzed), 2 reps, "
               "2 won / 22 lost / 42 open. Treat as leads to act on, not proof.")

    for c in cards:
        eg = (f'<div class="ew-eg">Heard on: {", ".join(c["examples"])}</div>'
              if c.get("examples") else "")
        st.markdown(
            f'<div class="ew-insight {c["tone"]}">'
            f'<div class="ew-src">{c["source"]}</div>'
            f'<div style="display:flex;gap:18px;align-items:baseline;">'
            f'<span class="ew-stat">{_stat(c)}</span>'
            f'<span class="ew-claim">{c["claim"]}</span></div>{eg}</div>',
            unsafe_allow_html=True)

    st.divider()
    st.subheader("The numbers behind it")
    agg = data.corpus_aggregate(marker)
    ranking = data.best_call_ranking(marker)
    if agg:
        a, b = st.columns(2)
        with a:
            st.plotly_chart(charts.pricing_tiers(agg), use_container_width=True)
            st.caption("Reps almost never name a current tier — “other” = the retired "
                       "per-worker pricing. The pricing problem, visualized.")
        with b:
            ev = st.plotly_chart(charts.objection_families(agg), use_container_width=True,
                                 on_select="rerun", selection_mode="points",
                                 key="obj_fam_select")
            fams = list((agg.get("objection_families") or {}).keys())
            clicked = None
            try:
                pts = (ev["selection"]["points"] if ev and ev.get("selection") else [])
                if pts:
                    clicked = pts[0].get("y")
            except (TypeError, KeyError):
                clicked = None
            if clicked and clicked in fams:
                st.session_state["objection_family"] = clicked
                st.session_state["_nav"] = "Objections"
                st.rerun()
            st.caption("“Fit” (mostly build-vs-buy / wrong-fit) is the dominant pushback. "
                       "Click a bar — or use the button below — to drill in.")
            fcols = st.columns([3, 2])
            sel = fcols[0].selectbox("Drill into a family", fams, key="obj_fam_fallback",
                                     label_visibility="collapsed")
            if fcols[1].button("Objections deep-dive →", key="obj_drill"):
                st.session_state["objection_family"] = sel
                st.session_state["_nav"] = "Objections"
                st.rerun()
        c, d = st.columns(2)
        with c:
            st.plotly_chart(charts.composite_ranking(ranking, data.short_label_map(marker)),
                            use_container_width=True)
            st.caption("Your reference calls — study the top as the model; the bottom "
                       "show what stalls. Hover any bar for what drove the score.")
        with d:
            st.plotly_chart(charts.discovery_hist(agg), use_container_width=True)
            st.caption("Most calls land mid-range on discovery; top calls cover more "
                       "ground (budget & timeline), not just more questions.")

    st.divider()
    st.caption("📋 Recommended scripts are on the **Scripts** page (and in the "
               "deliverables below).")
    with st.expander("📄 Full deliverables + scripts"):
        combined = {k: v for k, v in data.DELIVERABLES.items() if k != "Action Items"}
        combined.update(data.SCRIPTS)
        labels = list(combined)
        tabs = st.tabs(labels)
        for tab, label in zip(tabs, labels):
            with tab:
                deliverable = combined[label]
                versions = data.list_deliverable_versions(marker, deliverable)
                if not versions:
                    st.caption("Not generated yet.")
                    continue
                v = st.selectbox("Version", versions, index=len(versions) - 1,
                                 key=f"v_{deliverable}")
                dd = data.read_deliverable(marker, deliverable, v)
                if dd.get("diff_md"):
                    with st.expander("What changed vs prior version"):
                        st.markdown(style.safe_md(dd["diff_md"]))
                st.markdown(style.safe_md(dd.get("md", "")))
