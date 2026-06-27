"""Run pipeline — operator controls + coverage. (Insights live on Takeaways.)"""
from __future__ import annotations

import streamlit as st

from ui import data, runners, style


def _run_panel(label, key, launch_fn, cmd, help_text, confirm=False):
    st.markdown(f"**{label}**")
    st.caption(help_text)
    run_id = st.session_state.get(f"run_{key}")
    meta = runners.poll(run_id) if run_id else runners.latest_run(key)
    running = bool(meta and meta.get("status") == "running")

    if confirm and not running:
        ok = st.checkbox("I understand this runs unattended and may take a while.",
                         key=f"cf_{key}")
    else:
        ok = True

    cols = st.columns([1, 1, 4])
    if cols[0].button("▶ Run", key=f"btn_{key}", disabled=running or not ok):
        meta = launch_fn()
        st.session_state[f"run_{key}"] = meta["run_id"]
        st.rerun()
    if running and cols[1].button("■ Stop", key=f"stop_{key}"):
        runners.stop(meta["run_id"])
        st.rerun()

    if meta:
        status = meta.get("status", "?")
        color = {"running": style.AMBER, "done": style.EMERALD,
                 "failed": style.ROSE, "stopped": style.SLATE}.get(status, style.SLATE)
        st.markdown(style.badge(status.upper(), color), unsafe_allow_html=True)
        log = runners.read_log(meta["run_id"]) or "(starting…)"
        if status == "failed" and "command not found" in log.lower():
            st.error("The Claude CLI wasn't found. Install/log in (`claude login`), "
                     "or use the copy-command below to run analysis in a terminal.")
        elif status == "failed" and ("authenticate" in log.lower() or "401" in log):
            st.error("The Claude CLI couldn't authenticate for the headless run. "
                     "An in-session Claude Code login can't be reused by a subprocess. "
                     "Fix it once with **`claude setup-token`** in a terminal (creates "
                     "reusable CLI credentials), then click Run again — or run the "
                     "**copy-command below** inside your own Claude Code session.")
        with st.expander("Log", expanded=(status == "running")):
            st.code(log, language="text")
        if status == "running":
            st.button("↻ Refresh", key=f"ref_{key}")
        elif status in ("done", "failed", "stopped") and st.session_state.get(f"run_{key}"):
            st.cache_data.clear()
            st.session_state.pop(f"run_{key}", None)
    with st.expander("Prefer the terminal? Copy the command"):
        st.code(runners.cmd_str(cmd), language="bash")


def render():
    st.header("Run pipeline")
    marker = data.last_sync_marker()
    k = data.overview_kpis(marker)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Calls", k["n_calls"])
    c2.metric("Transcribed", f"{k['pct_transcribed']:.0f}%", f"{k['n_present']}/{k['n_calls']}")
    c3.metric("Analyzed", f"{k['pct_analyzed']:.0f}%", f"{k['n_full']}/{k['n_calls']}")
    c4.metric("Deliverables", k["n_deliverables"])

    left, right = st.columns([1, 1])
    with right:
        st.subheader("Steps")
        from pipeline import transcribe as _t
        _backends = ["openai", "groq", "mlx"]
        _default_be = _t.DEFAULT_BACKEND if _t.DEFAULT_BACKEND in _backends else "openai"
        be = st.selectbox("Transcription backend", _backends,
                          index=_backends.index(_default_be), key="be")
        with st.container(border=True):
            import datetime as _dt
            cc = st.columns(2)
            d0 = cc[0].date_input("Window start", value=_dt.date(2026, 5, 1), key="wstart")
            d1 = cc[1].date_input("Window end", value=_dt.date(2026, 6, 1), key="wend")
            start, end = d0.isoformat(), d1.isoformat()
            inc = st.checkbox("Incremental (only changed)", value=True)
            notr = st.checkbox("Skip transcription", value=False)
            _run_panel("1 · Ingest + transcribe", "ingest",
                       lambda: runners.run_ingest(start, end, inc, notr, be),
                       runners.ingest_cmd(start, end, inc, notr, be),
                       "Pull the recorded-calls window from HubSpot and transcribe.")
        with st.container(border=True):
            pend = runners.pending_counts()
            n_pending = sum(v for v in pend.values() if v)
            if not runners.claude_available():
                st.warning("Claude CLI not detected — the AI analysis runs through it. "
                           "Install it and run `claude login`, or use the copy-command.")
            elif not runners.headless_auth_ready():
                st.warning("⚠️ One-click headless analysis needs reusable Claude CLI "
                           "credentials. Run **`claude setup-token`** once in a terminal, "
                           "then this button works. Otherwise run the copy-command inside "
                           "your own Claude Code session.")
            st.caption(f"{n_pending} analysis tasks pending.")
            _run_panel("2 · Analyze calls (AI)", "analysis",
                       runners.run_analysis, runners.analysis_cmd(),
                       "Runs the AI analysis over any un-analyzed calls, then rebuilds the "
                       "scores, charts, and deliverables. Idempotent — safe to re-run.",
                       confirm=True)
        with st.container(border=True):
            _run_panel("3 · Rebuild scores & insights", "rescore",
                       runners.run_rescore, runners.rescore_cmd(),
                       "Recompute the rankings, charts, and action items from existing "
                       "analysis (fast, no AI).")

    with left:
        st.subheader("What's been analyzed")
        cov = data.coverage_table(marker)
        if not cov.empty:
            for _, r in cov.iterrows():
                friendly = data.FRIENDLY_AGENT.get(r["agent"], r["agent"])
                bar = style.tier_badge(int(r["covered"]), int(r["total"]))
                st.markdown(
                    f'<div style="display:flex;justify-content:space-between;'
                    f'padding:4px 0;"><span>{friendly}</span>{bar}</div>',
                    unsafe_allow_html=True)
        st.caption("Each row = one analysis pass and how many calls it covers.")
