"""Objections drill-down — per family: taxonomy of sub-types, how they're handled,
and the outcome lean. Reached by clicking the Takeaways objection chart or the nav."""
from __future__ import annotations

import streamlit as st

from ui import charts, data, style

_FAM_LABEL = {"fit": "Fit / build-vs-buy", "risk": "Risk", "price": "Price",
              "quality": "Quality", "other": "Other"}


def _resolved_badge(rate) -> str:
    if rate is None:
        return ""
    color = style.EMERALD if rate >= 60 else (style.AMBER if rate >= 40 else style.ROSE)
    return style.badge(f"{rate:.0f}% resolved", color)


def _example(label, ex, companies):
    if not ex:
        return ""
    cid = ex.get("call_id")
    who = companies.get(cid, cid)
    why = ex.get("why", "")
    hq = ex.get("handling_quality")
    return f"**{label}:** {who}" + (f" (hq {hq})" if hq is not None else "") + (f" — {why}" if why else "")


def render():
    st.header("Objections")
    marker = data.last_sync_marker()
    cat = data.objection_catalog(marker)
    fams_data = cat.get("families") or {}
    if not fams_data or not cat.get("n_objections"):
        st.info("No objection catalog yet. Run **Rebuild scores & insights** (or analysis) "
                "on the Run pipeline page.")
        return

    companies = data.company_map(marker)
    # families ordered by count desc
    fams = [f for f in sorted(fams_data, key=lambda f: fams_data[f].get("n", 0), reverse=True)
            if fams_data[f].get("n")]
    default_fam = st.session_state.get("objection_family", fams[0])
    if default_fam not in fams:
        default_fam = fams[0]
    fam = st.radio("Family", fams, index=fams.index(default_fam), horizontal=True,
                   format_func=lambda f: f"{_FAM_LABEL.get(f, f)} ({fams_data[f]['n']})")
    st.session_state["objection_family"] = fam
    fc = fams_data[fam]

    st.caption("⚠️ Directional — 282 objections across 72 calls, 2 reps. "
               "Resolved = handled with quality ≥ 2.")

    k = st.columns(4)
    k[0].metric("Objections", fc.get("n"))
    k[1].metric("% of all", f"{fc.get('pct', 0):.0f}%")
    k[2].metric("Resolved", f"{fc.get('resolved_rate', 0):.0f}%")
    k[3].metric("Engaged", f"{fc.get('handled_pct', 0):.0f}%")

    c = st.columns(2)
    c[0].plotly_chart(charts.objection_techniques(fc), use_container_width=True)
    c[1].plotly_chart(charts.objection_handling_quality(fc), use_container_width=True)

    st.subheader(f"{_FAM_LABEL.get(fam, fam)} — objection sub-types")
    ana = (data.objection_analysis(marker).get("data") or {})
    afam = next((f for f in (ana.get("families") or []) if f.get("family") == fam), None)
    if not afam:
        st.caption("Sub-type analysis not generated yet — run the objection-analysis agent "
                   "(Run pipeline → Analyze calls). Showing raw objection labels below.")
        for inst in fc.get("top_example_calls", []):
            st.markdown(f"- *{inst.get('label')}* — {companies.get(inst.get('call_id'), '')}")
        return

    for s in afam.get("subtypes", []):
        with st.container(border=True):
            head = st.columns([6, 2])
            head[0].markdown(f"**{s.get('name')}** &nbsp; "
                             f'<span class="ew-eg">{s.get("n")} · '
                             f'{s.get("pct_of_family", 0):.0f}% of {fam}</span>',
                             unsafe_allow_html=True)
            head[1].markdown(_resolved_badge(s.get("resolved_rate")), unsafe_allow_html=True)
            if s.get("description"):
                st.caption(s["description"])
            # verbatim quote(s)
            for q in (s.get("quotes") or [])[:2]:
                who = companies.get(q.get("call_id"), q.get("call_id"))
                st.markdown(f"> {style.safe_md(q.get('text', ''))}  \n"
                            f"<span class='ew-eg'>— {who}</span>", unsafe_allow_html=True)
            # techniques used
            td = s.get("techniques_used") or {}
            if td:
                st.markdown(" ".join(style.badge(f"{kk} {vv}", style.SLATE)
                                     for kk, vv in td.items()), unsafe_allow_html=True)
            best = _example("Best handled", s.get("best_handled"), companies)
            worst = _example("Weakest", s.get("worst_handled"), companies)
            if best:
                st.markdown(style.safe_md(best))
            if worst:
                st.markdown(style.safe_md(worst))
            if s.get("outcome_signal"):
                st.markdown(f"📈 **Outcome lean:** {style.safe_md(s['outcome_signal'])}")
            if s.get("recommended_handling"):
                st.markdown(f"✅ **Recommended:** {style.safe_md(s['recommended_handling'])}")

    st.caption("📋 Word-for-word identification + response scripts are on the "
               "**Scripts** page (Objection Handling Script).")
