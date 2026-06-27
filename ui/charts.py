"""Pure Plotly figure builders (data in -> go.Figure out). Emerald palette."""
from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from ui import style

_LAYOUT = dict(
    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
    font_color=style.TEXT, margin=dict(l=10, r=10, t=40, b=10), height=320,
    legend=dict(bgcolor="rgba(0,0,0,0)"),
)


def _apply(fig: go.Figure, title: str | None = None) -> go.Figure:
    fig.update_layout(**_LAYOUT)
    if title:
        fig.update_layout(title=dict(text=title, font=dict(size=14)))
    fig.update_xaxes(gridcolor="#e2e8f0", zerolinecolor="#e2e8f0", linecolor="#cbd5e1")
    fig.update_yaxes(gridcolor="#e2e8f0", zerolinecolor="#e2e8f0", linecolor="#cbd5e1")
    return fig


def objection_families(agg: dict) -> go.Figure:
    fam = agg.get("objection_families", {})
    if not fam:
        return _apply(go.Figure())
    df = pd.DataFrame([{"family": k, "n": v["n"]} for k, v in fam.items()]).sort_values("n")
    colors = [style.OBJECTION_COLOR.get(f, style.SLATE) for f in df["family"]]
    fig = go.Figure(go.Bar(x=df["n"], y=df["family"], orientation="h",
                           marker_color=colors, text=df["n"], textposition="auto"))
    return _apply(fig, "Objections by family")


def pricing_tiers(agg: dict) -> go.Figure:
    tiers = (agg.get("pricing", {}) or {}).get("tiers_mentioned", {})
    order = ["Starter", "Scale", "Advanced", "other"]
    vals = {k: tiers.get(k, 0) for k in order}
    colors = [style.EMERALD, style.EMERALD, style.EMERALD, style.ROSE]
    fig = go.Figure(go.Bar(x=order, y=[vals[k] for k in order],
                           marker_color=colors, text=[vals[k] for k in order],
                           textposition="auto"))
    return _apply(fig, "Pricing tiers named on calls  (‘other’ = dead model)")


def buyer_reaction(agg: dict) -> go.Figure:
    rx = (agg.get("pricing", {}) or {}).get("buyer_reaction", {})
    order = ["positive", "neutral", "negative", "none"]
    vals = [rx.get(k, 0) for k in order]
    colors = [style.SENTIMENT_COLOR[k] for k in order]
    fig = go.Figure(go.Bar(x=order, y=vals, marker_color=colors, text=vals, textposition="auto"))
    return _apply(fig, "Buyer reaction when pricing came up")


def icp_donut(agg: dict, key: str, title: str) -> go.Figure:
    d = (agg.get("icp", {}) or {}).get(key, {})
    if not d:
        return _apply(go.Figure())
    labels = list(d.keys())
    colors = ([style.ICP_COLOR.get(str(l), style.SLATE) for l in labels]
              if key == "tiers" else style.SEQ)
    fig = go.Figure(go.Pie(labels=labels, values=list(d.values()), hole=0.55,
                           marker=dict(colors=colors)))
    return _apply(fig, title)


_COMP_LABELS = {"stage_progression": "deal stage", "next_step": "next step",
                "engagement": "engagement", "discovery": "discovery",
                "objection_handling": "objections", "amount_percentile": "deal size"}


def composite_ranking(ranked: pd.DataFrame, labels: dict | None = None,
                      top: int = 8, bottom: int = 5) -> go.Figure:
    """Reference calls: the top exemplars and the bottom cautionary calls, labeled
    by account, colored by outcome, with the score drivers on hover."""
    if ranked.empty:
        return _apply(go.Figure())
    labels = labels or {}
    df = ranked.copy()
    # drop degenerate (composite 0) from the cautionary end so it teaches something
    nz = df[df["composite_score"] > 0]
    head = nz.head(top)
    tail = nz.tail(bottom)
    sel = pd.concat([head, tail]).drop_duplicates("call_id")
    sel = sel.sort_values("composite_score")  # ascending -> best on top in a horizontal bar

    def _why(row):
        comps = row.get("components") or {}
        ranked_c = sorted(((_COMP_LABELS.get(k, k), v) for k, v in comps.items()
                           if isinstance(v, (int, float))), key=lambda kv: kv[1], reverse=True)
        if not ranked_c:
            return ""
        best = ranked_c[0]
        worst = ranked_c[-1]
        return f"strongest: {best[0]} · weakest: {worst[0]}"

    y = [labels.get(c, c) for c in sel["call_id"]]
    # de-dup identical account labels by appending a marker
    seen = {}
    y2 = []
    for lab in y:
        seen[lab] = seen.get(lab, 0) + 1
        y2.append(lab if seen[lab] == 1 else f"{lab} ({seen[lab]})")
    colors = [style.OUTCOME_COLOR.get(s, style.SLATE) for s in sel["deal_status"]]
    custom = list(zip(sel["deal_status"], [_why(r) for _, r in sel.iterrows()]))
    fig = go.Figure(go.Bar(
        x=sel["composite_score"], y=y2, orientation="h", marker_color=colors,
        text=[f"{v:.0f}" for v in sel["composite_score"]], textposition="outside",
        customdata=custom,
        hovertemplate="<b>%{y}</b><br>score %{x:.0f} · %{customdata[0]}<br>%{customdata[1]}<extra></extra>"))
    fig.update_xaxes(range=[0, max(100, sel["composite_score"].max() + 8)])
    return _apply(fig, "Reference calls: best vs. needs-work (color = outcome)")


def discovery_hist(agg: dict) -> go.Figure:
    scores = [s.get("score") for s in (agg.get("discovery", {}) or {}).get("scores", [])
              if s.get("score") is not None]
    if not scores:
        return _apply(go.Figure())
    fig = go.Figure(go.Histogram(x=scores, nbinsx=10, marker_color=style.EMERALD))
    mean = (agg.get("discovery", {}) or {}).get("mean")
    if mean:
        fig.add_vline(x=mean, line_color=style.AMBER, line_dash="dash",
                      annotation_text=f"mean {mean}")
    return _apply(fig, "Discovery score distribution")


def objection_techniques(fc: dict) -> go.Figure:
    d = fc.get("technique_dist", {}) or {}
    order = ["acknowledge", "reframe", "evidence", "deflect", "ignore"]
    vals = [d.get(k, 0) for k in order]
    colors = [style.SLATE, style.EMERALD, style.INFO, style.AMBER, style.ROSE]
    fig = go.Figure(go.Bar(x=order, y=vals, marker_color=colors, text=vals,
                           textposition="auto"))
    return _apply(fig, "How this family is handled (technique)")


def objection_handling_quality(fc: dict) -> go.Figure:
    d = fc.get("handling_quality_dist", {}) or {}
    labels = ["0 · unhandled", "1 · weak", "2 · solid", "3 · strong"]
    vals = [d.get(k, 0) for k in ["0", "1", "2", "3"]]
    colors = [style.ROSE, style.AMBER, style.SLATE, style.EMERALD]
    fig = go.Figure(go.Bar(x=labels, y=vals, marker_color=colors, text=vals,
                           textposition="auto"))
    return _apply(fig, "Handling quality")


def phase_timeline(phases: list[dict]) -> go.Figure:
    if not phases:
        return _apply(go.Figure())
    df = pd.DataFrame([{"phase": p.get("name", "?"),
                        "start": p.get("start_turn", 0), "end": p.get("end_turn", 0)}
                       for p in phases])
    df["width"] = (df["end"] - df["start"]).clip(lower=1)
    fig = go.Figure()
    for i, r in df.iterrows():
        fig.add_trace(go.Bar(x=[r["width"]], y=["flow"], base=r["start"], orientation="h",
                             name=r["phase"], marker_color=style.SEQ[i % len(style.SEQ)],
                             hovertemplate=f"{r['phase']}: turns {r['start']}–{r['end']}<extra></extra>"))
    fig.update_layout(barmode="stack", showlegend=True)
    fig = _apply(fig, "Call structure (turn ranges)")
    fig.update_layout(height=180)
    return fig
