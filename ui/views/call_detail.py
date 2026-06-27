"""Per-call deep view: transcript with roles + every per-call agent result."""
from __future__ import annotations

import streamlit as st

from ui import charts, data, style


def _role_class(role):
    return {"rep": "ew-turn-rep", "customer": "ew-turn-cust"}.get(role, "ew-turn-unk")


def render():
    st.header("Call detail")
    marker = data.last_sync_marker()
    calls = data.calls_table(marker)
    if calls.empty:
        st.info("No calls yet.")
        return

    id_to_label = dict(zip(calls["call_id"], calls["label"]))
    label_to_id = {v: k for k, v in id_to_label.items()}
    ids = list(calls["call_id"])
    sel = st.session_state.get("selected_call", ids[0])
    sel_label = st.selectbox("Choose a call", list(label_to_id.keys()),
                             index=list(id_to_label.values()).index(id_to_label[sel])
                             if sel in id_to_label else 0)
    sel = label_to_id[sel_label]
    st.session_state["selected_call"] = sel

    detail = data.call_detail(marker, sel)
    ctx, ag = detail["context"], detail["agents"]
    sa = ag.get("speaker_attribution") or {}
    dq = ag.get("discovery_quality") or {}
    oh = ag.get("objection_handling") or {}
    ns = ag.get("commitment_next_step") or {}
    ic = ag.get("icp_fit_tagger") or {}
    pr = ag.get("pricing_packaging_reaction") or {}
    cm = ag.get("competitive_mention") or {}
    cs = ag.get("call_structure") or {}

    rep = (ctx.get("rep") or {}).get("name", "—")
    company = next((c["name"] for c in ctx.get("companies", []) if c["name"] != "EverWorker"), "—")
    deal = (ctx.get("deals") or [{}])[0]
    st.markdown(f'<div class="ew-hero"><h1>{ctx.get("title") or sel}</h1>'
                f'<p>Rep: {rep} · {company} · Deal: {deal.get("stage_label","—")} '
                f'({deal.get("status","—")})</p></div>', unsafe_allow_html=True)

    m = st.columns(5)
    m[0].metric("Discovery", dq.get("score", "—"))
    m[1].metric("Objection handling", oh.get("overall_handling", "—"))
    m[2].metric("Next step (0-3)", ns.get("strength", "—"))
    m[3].metric("ICP tier", ic.get("icp_tier", "—"))
    m[4].metric("Attribution conf.", sa.get("attribution_confidence", "—"))

    if not dq:
        st.warning("This call hasn't been analyzed yet (or is a degenerate transcript). "
                   "Run analysis from the Overview page.")

    tabs = st.tabs(["Transcript", "Discovery", "Objections", "Pricing",
                    "Next step · ICP", "Competitors", "Structure"])

    with tabs[0]:
        roles = {t["i"]: t.get("role") for t in sa.get("turns", [])}
        names = {p["participant_id"]: p["name"] for p in sa.get("participants", [])
                 if p.get("participant_id")}
        turns = ctx.get("turns", [])
        st.caption(f"{len(turns)} turns · {sa.get('n_rep_turns','?')} rep / "
                   f"{sa.get('n_customer_turns','?')} customer")
        limit = st.slider("Show first N turns", 20, max(len(turns), 20),
                          min(120, len(turns)))
        html = []
        for t in turns[:limit]:
            role = roles.get(t["i"], "unknown")
            tag = {"rep": "REP", "customer": "CUSTOMER"}.get(role, "?")
            html.append(f'<div class="{_role_class(role)}">'
                        f'<span class="ew-role">{tag}</span> &nbsp;{t["text"]}</div>')
        st.markdown("".join(html), unsafe_allow_html=True)

    with tabs[1]:
        if dq:
            bant = dq.get("bant", {})
            st.write("**BANT:** " + " · ".join(
                f"{k.title()} {'✅' if bant.get(k) else '—'}"
                for k in ["budget", "authority", "need", "timeline"]))
            st.write(f"Open-question ratio: {dq.get('open_question_ratio','—')} · "
                     f"pains uncovered: {dq.get('pains_uncovered','—')}")
            st.write("**Strengths**"); st.write(dq.get("strengths", []))
            st.write("**Gaps**"); st.write(dq.get("gaps", []))
        else:
            st.caption("No discovery analysis.")

    with tabs[2]:
        objs = oh.get("objections", [])
        if objs:
            import pandas as pd
            st.dataframe(pd.DataFrame(objs), width='stretch', hide_index=True)
        else:
            st.caption("No objections recorded.")

    with tabs[3]:
        if pr:
            st.write(f"**Pricing discussed:** {pr.get('pricing_discussed')} · "
                     f"reaction: {pr.get('buyer_reaction')} · "
                     f"price objection: {pr.get('price_objection')}")
            st.write(f"**Tiers mentioned:** {pr.get('tiers_mentioned')} · "
                     f"anchor: {pr.get('anchor_value')}")
            st.write(f"**Rep framing:** {pr.get('rep_framing','')}")
            if pr.get("bundling_signals"):
                st.write("**Bundling signals**"); st.write(pr["bundling_signals"])
        else:
            st.caption("No pricing analysis.")

    with tabs[4]:
        st.write(f"**Next step:** {ns.get('next_step_type','—')} · "
                 f"owner: {ns.get('who_owns','—')} · secured: {ns.get('next_step_secured','—')} "
                 f"· strength {ns.get('strength','—')}")
        if ns.get("explicit_quote"):
            st.caption(f"“{ns['explicit_quote']}”")
        st.divider()
        st.write(f"**ICP tier {ic.get('icp_tier','—')}** · {ic.get('persona_family','—')} · "
                 f"{ic.get('industry','—')} · {ic.get('size_band','—')}")
        st.write(ic.get("rationale", ""))
        if ic.get("fit_signals"):
            st.write("Fit:", ic["fit_signals"])
        if ic.get("anti_fit_signals"):
            st.write("Anti-fit:", ic["anti_fit_signals"])

    with tabs[5]:
        comps = cm.get("competitors", [])
        if comps:
            import pandas as pd
            st.dataframe(pd.DataFrame(comps), width='stretch', hide_index=True)
            st.caption(f"prior vendor failure cited: {cm.get('prior_vendor_failure_cited')}")
        else:
            st.caption("No competitor mentions.")

    with tabs[6]:
        if cs.get("phases"):
            st.plotly_chart(charts.phase_timeline(cs["phases"]), use_container_width=True)
            st.write(f"Followed expected sequence: {cs.get('followed_expected_sequence')} · "
                     f"time to first discovery Q: turn {cs.get('time_to_first_discovery_q')}")
            st.caption(cs.get("sequence_notes", ""))
        else:
            st.caption("No structure analysis.")
