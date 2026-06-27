"""Cached read layer for the dashboard — the ONLY module that touches the store /
outputs. Every reader is @st.cache_data(ttl=300) keyed on a `_marker` so a write
(agent result or a re-versioned deliverable) busts the cache.

Reuses pipeline.store + skills.store_io.* — no new SQL logic.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pandas as pd
import streamlit as st

from pipeline import store
from skills.store_io import context_loader, registry, results_io

REPO_ROOT = Path(__file__).resolve().parents[1]
# Honor the same env vars the pipeline + skills use, so the dashboard reads from
# the same place writes land — including a mounted volume on Railway. Falls back
# to the in-repo dirs for local dev.
DATA_DIR = Path(os.environ.get("DATA_DIR", str(REPO_ROOT / "data"))).resolve()
OUTPUTS_DIR = Path(os.environ.get("OUTPUTS_DIR", str(REPO_ROOT / "outputs"))).resolve()
CACHE_TTL = 300

PER_CALL_AGENTS = [
    "speaker_attribution", "rep_talk_extraction", "customer_voice_extraction",
    "discovery_quality", "objection_handling", "pricing_packaging_reaction",
    "call_structure", "competitive_mention", "commitment_next_step", "icp_fit_tagger",
]
# friendly label -> outputs/<dir> (encodes the agent-name vs dir-name gotcha)
DELIVERABLES = {
    "Rubric": "rubric",
    "Pricing & Packaging": "pricing_packaging_insights",
    "Discovery Playbook": "discovery_playbook",
    "Sequence Analysis": "sales_call_sequence_script",
    "Objection Analysis": "objection_analysis",
    "Action Items": "action_items",
}

# Rep-facing recommended scripts (word-for-word talk tracks). Same versioned
# plumbing as DELIVERABLES; rendered on the dedicated Scripts page + in the
# deliverables expander.
SCRIPTS = {
    "Pricing & Packaging Script": "pricing_script",
    "Discovery Script": "discovery_script",
    "Call Sequence Script": "sequence_script",
    "Objection Handling Script": "objection_script",
}

# plain-language names for the technical agents (used in coverage)
FRIENDLY_AGENT = {
    "speaker_attribution": "Who-spoke labeling",
    "rep_talk_extraction": "Rep talk (questions, pitch)",
    "customer_voice_extraction": "Customer voice (pains, objections)",
    "discovery_quality": "Discovery scoring",
    "objection_handling": "Objection handling",
    "pricing_packaging_reaction": "Pricing reactions",
    "call_structure": "Call structure",
    "competitive_mention": "Competitor mentions",
    "commitment_next_step": "Next-step securing",
    "icp_fit_tagger": "ICP fit",
}


def _short_date(ts) -> str:
    try:
        return pd.to_datetime(ts).strftime("%b %-d")
    except Exception:
        return ""


def make_label(company, rep, ts) -> str:
    """A human, recognizable label for a call: 'Ocean.io · May 1 · Nicole'."""
    parts = [str(company) if company else (str(rep) if rep else "Unknown call")]
    d = _short_date(ts)
    if d:
        parts.append(d)
    if company and rep:  # only add rep first-name when account is the primary label
        parts.append(str(rep).split()[0])
    return " · ".join(parts)


# ---------------- cache marker ---------------- #

@st.cache_data(ttl=CACHE_TTL)
def last_sync_marker() -> str:
    """max(created_at) in analysis_results ++ newest mtime under outputs/."""
    with store.connect() as conn:
        ts = conn.execute("SELECT MAX(created_at) FROM analysis_results").fetchone()[0]
    mt = 0.0
    if OUTPUTS_DIR.exists():
        for p in OUTPUTS_DIR.rglob("*"):
            if p.is_file():
                mt = max(mt, p.stat().st_mtime)
    return f"{ts}|{mt:.0f}"


# ---------------- overview ---------------- #

@st.cache_data(ttl=CACHE_TTL)
def overview_kpis(_marker: str) -> dict:
    with store.connect() as conn:
        n_calls = conn.execute("SELECT COUNT(*) FROM calls").fetchone()[0]
        n_present = conn.execute(
            "SELECT COUNT(*) FROM calls WHERE transcript_status='present'").fetchone()[0]
        # fully analyzed = has all 10 per-call agents
        rows = conn.execute(
            "SELECT call_id, COUNT(DISTINCT agent) n FROM analysis_results "
            "WHERE agent IN ({}) GROUP BY call_id".format(
                ",".join("?" * len(PER_CALL_AGENTS))), PER_CALL_AGENTS).fetchall()
        n_full = sum(1 for r in rows if r["n"] >= len(PER_CALL_AGENTS))
        last_at = conn.execute("SELECT MAX(created_at) FROM analysis_results").fetchone()[0]
    n_deliv = sum(1 for d in set(DELIVERABLES.values())
                  if (OUTPUTS_DIR / d).exists() and any((OUTPUTS_DIR / d).glob("v*.json")))
    return {"n_calls": n_calls, "n_present": n_present, "n_full": n_full,
            "pct_transcribed": (100 * n_present / n_calls) if n_calls else 0,
            "pct_analyzed": (100 * n_full / n_calls) if n_calls else 0,
            "n_deliverables": n_deliv, "last_analysis_at": last_at}


@st.cache_data(ttl=CACHE_TTL)
def coverage_table(_marker: str) -> pd.DataFrame:
    rows = []
    with store.connect() as conn:
        total = conn.execute(
            "SELECT COUNT(*) FROM calls WHERE transcript_status='present'").fetchone()[0]
        for agent, meta in registry.AGENTS.items():
            if meta.get("corpus"):
                continue
            covered = conn.execute(
                "SELECT COUNT(DISTINCT call_id) FROM analysis_results WHERE agent=?",
                (agent,)).fetchone()[0]
            rows.append({"agent": agent, "stage": meta["stage"],
                         "covered": covered, "total": total,
                         "pending": max(total - covered, 0)})
    return pd.DataFrame(rows)


# ---------------- calls ---------------- #

@st.cache_data(ttl=CACHE_TTL)
def calls_table(_marker: str) -> pd.DataFrame:
    with store.connect() as conn:
        base = conn.execute("""
            SELECT ca.call_id, ca.hs_timestamp, ca.transcript_status,
                   o.full_name AS rep,
                   (SELECT co.name FROM companies co JOIN call_companies cc
                      ON cc.company_id=co.company_id WHERE cc.call_id=ca.call_id
                      AND co.name != 'EverWorker' LIMIT 1) AS company,
                   (SELECT ct.job_title FROM contacts ct JOIN call_contacts cc
                      ON cc.contact_id=ct.contact_id WHERE cc.call_id=ca.call_id LIMIT 1) AS persona_title,
                   (SELECT d.status FROM deals d JOIN call_deals cd
                      ON cd.deal_id=d.deal_id WHERE cd.call_id=ca.call_id LIMIT 1) AS deal_status,
                   (SELECT d.stage_label FROM deals d JOIN call_deals cd
                      ON cd.deal_id=d.deal_id WHERE cd.call_id=ca.call_id LIMIT 1) AS deal_stage,
                   (SELECT d.amount FROM deals d JOIN call_deals cd
                      ON cd.deal_id=d.deal_id WHERE cd.call_id=ca.call_id LIMIT 1) AS amount
            FROM calls ca LEFT JOIN owners o ON o.owner_id=ca.owner_id
            ORDER BY ca.hs_timestamp
        """).fetchall()
        rows = [dict(r) for r in base]
        # composite scores from the corpus ranking
        ranking = store.latest_analysis(conn, registry.CORPUS_ID, "best_performing_call") or {}
        comp = {r["call_id"]: r["composite_score"] for r in ranking.get("ranked", [])}
        for row in rows:
            cid = row["call_id"]
            dq = store.latest_analysis(conn, cid, "discovery_quality")
            oh = store.latest_analysis(conn, cid, "objection_handling")
            ns = store.latest_analysis(conn, cid, "commitment_next_step")
            ic = store.latest_analysis(conn, cid, "icp_fit_tagger")
            row["discovery"] = (dq or {}).get("score")
            row["n_objections"] = (oh or {}).get("n_objections")
            row["next_step"] = bool((ns or {}).get("next_step_secured")) if ns else None
            row["next_step_strength"] = (ns or {}).get("strength")
            row["icp_tier"] = str((ic or {}).get("icp_tier")) if ic else None
            row["persona"] = (ic or {}).get("persona_family")
            row["composite"] = comp.get(cid)
            row["deal_status"] = row["deal_status"] or "no_deal"
            row["analyzed"] = dq is not None
            row["label"] = make_label(row.get("company"), row.get("rep"),
                                       row.get("hs_timestamp"))
            row["persona"] = row.get("persona") or row.get("persona_title")
    return pd.DataFrame(rows)


@st.cache_data(ttl=CACHE_TTL)
def label_map(_marker: str) -> dict:
    """call_id -> human label, for chips/selectors anywhere."""
    df = calls_table(_marker)
    return dict(zip(df["call_id"], df["label"])) if not df.empty else {}


@st.cache_data(ttl=CACHE_TTL)
def company_map(_marker: str) -> dict:
    df = calls_table(_marker)
    if df.empty:
        return {}
    return {r["call_id"]: (r["company"] or r["rep"] or r["call_id"])
            for _, r in df.iterrows()}


@st.cache_data(ttl=CACHE_TTL)
def short_label_map(_marker: str) -> dict:
    """call_id -> 'Account (Rep)' — compact label for chart axes."""
    df = calls_table(_marker)
    if df.empty:
        return {}
    out = {}
    for _, r in df.iterrows():
        acct = r["company"] or r["rep"] or "Unknown"
        rep = (str(r["rep"]).split()[0] if r["rep"] else "")
        out[r["call_id"]] = f"{acct} ({rep})" if (r["company"] and rep) else str(acct)
    return out


@st.cache_data(ttl=CACHE_TTL)
def headlines(_marker: str) -> list[dict]:
    """One distinct, bold insight per theme — no redundancy. Account-only examples."""
    comp = company_map(_marker)
    tone = {"pricing_packaging_insights": "bad",
            "sales_call_sequence_script": "good",
            "discovery_playbook": "info"}

    def top_finding(deliverable):
        d = read_deliverable(_marker, deliverable, None)
        fs = [f for f in (d.get("data", {}) or {}).get("findings", []) or []
              if isinstance(f, dict)]
        if not fs:
            return None
        f = max(fs, key=lambda x: (x.get("support", {}) or {}).get("pct") or 0)
        sup = f.get("support", {}) or {}
        ex = []
        for c in (sup.get("example_calls") or []):
            name = comp.get(c, c)
            if name not in ex:
                ex.append(name)
            if len(ex) >= 3:
                break
        return {"tone": tone.get(deliverable, "info"),
                "source": [k for k, v in DELIVERABLES.items() if v == deliverable][0],
                "claim": f.get("claim", ""), "pct": sup.get("pct"),
                "n_calls": sup.get("n_calls"), "examples": ex}

    cards = [c for c in (top_finding("pricing_packaging_insights"),
                         top_finding("sales_call_sequence_script"),
                         top_finding("discovery_playbook")) if c]

    # one objection-mix insight straight from the aggregate (distinct theme)
    agg = corpus_aggregate(_marker)
    fams = agg.get("objection_families", {})
    if fams:
        total = sum(v["n"] for v in fams.values()) or 1
        top = max(fams.items(), key=lambda kv: kv[1]["n"])
        ex = []
        for e in (top[1].get("examples") or []):
            name = comp.get(e.get("call_id"), "")
            if name and name not in ex:
                ex.append(name)
            if len(ex) >= 3:
                break
        cards.append({
            "tone": "info", "source": "Objections",
            "claim": f"“{top[0].capitalize()}” is the most common pushback "
                     f"({top[1]['n']} of {total} objections) — more than price or risk. "
                     f"Mostly build-vs-buy and wrong-fit.",
            "pct": round(100 * top[1]["n"] / total), "n_calls": None, "examples": ex})
    return cards


@st.cache_data(ttl=CACHE_TTL)
def call_detail(_marker: str, call_id: str) -> dict:
    ctx = context_loader.load_call_context(call_id)
    with store.connect() as conn:
        agents = {a: store.latest_analysis(conn, call_id, a) for a in PER_CALL_AGENTS}
    return {"context": ctx, "agents": agents}


# ---------------- corpus + deliverables ---------------- #

@st.cache_data(ttl=CACHE_TTL)
def corpus_aggregate(_marker: str) -> dict:
    p = DATA_DIR / "results" / "corpus_aggregate.json"
    if p.exists():
        return json.loads(p.read_text())
    return {}


@st.cache_data(ttl=CACHE_TTL)
def best_call_ranking(_marker: str) -> pd.DataFrame:
    with store.connect() as conn:
        r = store.latest_analysis(conn, registry.CORPUS_ID, "best_performing_call") or {}
    return pd.DataFrame(r.get("ranked", []))


@st.cache_data(ttl=CACHE_TTL)
def list_deliverable_versions(_marker: str, deliverable: str) -> list[int]:
    d = OUTPUTS_DIR / deliverable
    vs = []
    if d.exists():
        for p in d.glob("v*.json"):
            try:
                vs.append(int(p.stem[1:]))
            except ValueError:
                pass
    return sorted(vs)


@st.cache_data(ttl=CACHE_TTL)
def read_deliverable(_marker: str, deliverable: str, version: int | None) -> dict:
    d = OUTPUTS_DIR / deliverable
    versions = list_deliverable_versions(_marker, deliverable)
    if not versions:
        return {}
    v = version or versions[-1]
    md = (d / f"v{v}.md").read_text() if (d / f"v{v}.md").exists() else ""
    diff = (d / f"v{v}.diff.md").read_text() if (d / f"v{v}.diff.md").exists() else ""
    data = json.loads((d / f"v{v}.json").read_text()) if (d / f"v{v}.json").exists() else {}
    return {"version": v, "versions": versions, "md": md, "diff_md": diff, "data": data}


@st.cache_data(ttl=CACHE_TTL)
def objection_catalog(_marker: str) -> dict:
    p = DATA_DIR / "results" / "objection_catalog.json"
    return json.loads(p.read_text()) if p.exists() else {}


@st.cache_data(ttl=CACHE_TTL)
def objection_analysis(_marker: str) -> dict:
    return read_deliverable(_marker, "objection_analysis", None)


@st.cache_data(ttl=CACHE_TTL)
def action_items(_marker: str) -> pd.DataFrame:
    d = OUTPUTS_DIR / "action_items"
    versions = list_deliverable_versions(_marker, "action_items")
    if not versions:
        return pd.DataFrame()
    data = json.loads((d / f"v{versions[-1]}.json").read_text())
    return pd.DataFrame(data.get("items", []))
