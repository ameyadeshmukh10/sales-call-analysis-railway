"""Assemble per-call context for an agent, and compute the resumable worklist.

Deterministic reads over the SQLite store + transcript files. No LLM calls.

`load_call_context` gives an agent everything it needs in one envelope: the known
participants (rep + customer contacts — the anchors for speaker attribution),
firmographics, deal outcome, and the ordered, index-tagged transcript turns.

`list_pending` is what makes the orchestrator idempotent and resumable: it
returns only the calls that still need `agent` at its current prompt_version, and
(via the dependency gate) only those whose prerequisite agents are already
satisfied — so Stage B never runs on a call that lacks Stage A.

CLI:
  python -m skills.store_io.context_loader context '{"call_id":"489376191737"}'
  python -m skills.store_io.context_loader pending '{"agent":"speaker_attribution"}'
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from pipeline import store
from skills.common.io_contract import emit, emit_error, read_params
from skills.store_io import registry

DATA_DIR = Path(os.environ.get("DATA_DIR", "./data")).resolve()
TRANSCRIPT_DIR = DATA_DIR / "transcripts"


# ---------------- per-call context ---------------- #

def _load_turns(call_id: str) -> list[dict]:
    path = TRANSCRIPT_DIR / f"{call_id}.json"
    if not path.exists():
        return []
    data = json.loads(path.read_text())
    turns = []
    for i, t in enumerate(data.get("turns", [])):
        turns.append({"i": i, "text": t.get("text", ""),
                      "start_ms": t.get("start_ms"), "end_ms": t.get("end_ms")})
    return turns


def load_call_context(call_id: str) -> dict:
    with store.connect() as conn:
        call = conn.execute("SELECT * FROM calls WHERE call_id=?", (call_id,)).fetchone()
        if call is None:
            raise KeyError(f"no call {call_id}")
        rep = None
        if call["owner_id"]:
            o = conn.execute("SELECT * FROM owners WHERE owner_id=?",
                             (call["owner_id"],)).fetchone()
            if o:
                rep = {"owner_id": o["owner_id"], "name": o["full_name"],
                       "email": o["email"]}
        contacts = []
        for r in conn.execute(
                "SELECT c.* FROM contacts c JOIN call_contacts cc "
                "ON cc.contact_id=c.contact_id WHERE cc.call_id=?", (call_id,)):
            contacts.append({"contact_id": r["contact_id"], "name": r["full_name"],
                             "job_title": r["job_title"], "company_name": r["company_name"]})
        companies = []
        for r in conn.execute(
                "SELECT co.* FROM companies co JOIN call_companies cc "
                "ON cc.company_id=co.company_id WHERE cc.call_id=?", (call_id,)):
            companies.append({"company_id": r["company_id"], "name": r["name"],
                              "industry": r["industry"], "num_employees": r["num_employees"],
                              "annual_revenue": r["annual_revenue"], "country": r["country"]})
        deals = []
        for r in conn.execute(
                "SELECT d.* FROM deals d JOIN call_deals cd ON cd.deal_id=d.deal_id "
                "WHERE cd.call_id=?", (call_id,)):
            deals.append({"deal_id": r["deal_id"], "name": r["name"],
                          "stage_label": r["stage_label"], "status": r["status"],
                          "amount": r["amount"], "is_won": r["is_won"],
                          "is_closed": r["is_closed"], "close_date": r["close_date"]})

    turns = _load_turns(call_id)
    return {
        "call_id": call_id,
        "title": call["title"],
        "timestamp": call["hs_timestamp"],
        "duration_ms": call["duration_ms"],
        "direction": call["direction"],
        "rep": rep,
        "contacts": contacts,
        "companies": companies,
        "deals": deals,
        "n_turns": len(turns),
        "turns": turns,
    }


# ---------------- worklist / dependency gate ---------------- #

def _has_current(conn, call_id: str, agent: str) -> bool:
    """True if `call_id` has a stored `agent` result at >= the current prompt_version."""
    res = store.latest_analysis(conn, call_id, agent)
    if res is None:
        return False
    return int(res.get("_prompt_version", 0)) >= registry.prompt_version(agent)


def list_pending(agent: str, *, require_stage_a: bool | None = None) -> list[str]:
    """call_ids that still need `agent` and whose prerequisites are satisfied.

    A call is pending when it has a transcript, lacks a current-version result for
    `agent`, and has current results for every agent in registry.requires(agent).
    `require_stage_a` is kept for explicitness but the dependency list already
    encodes it; when None we use the registry.
    """
    deps = list(registry.requires(agent))
    if require_stage_a and "speaker_attribution" not in deps:
        deps.append("speaker_attribution")

    pending: list[str] = []
    with store.connect() as conn:
        rows = conn.execute(
            "SELECT call_id FROM calls WHERE transcript_status='present' "
            "ORDER BY hs_timestamp").fetchall()
        for r in rows:
            cid = r["call_id"]
            if _has_current(conn, cid, agent):
                continue  # already done at current version
            if all(_has_current(conn, cid, d) for d in deps):
                pending.append(cid)
    return pending


def load_prior_results(call_id: str, agents: list[str]) -> dict:
    """Bundle the latest result for each requested agent (None if absent)."""
    out: dict[str, dict | None] = {}
    with store.connect() as conn:
        for a in agents:
            out[a] = store.latest_analysis(conn, call_id, a)
    return out


# ---------------- CLI ---------------- #

def _main() -> None:
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if len(sys.argv) > 2:
        sys.argv = [sys.argv[0], sys.argv[2]]
    else:
        sys.argv = [sys.argv[0]]
    params = read_params()

    if cmd == "context":
        try:
            ctx = load_call_context(params["call_id"])
            emit({"results": ctx,
                  "summary": f"Loaded context for {params['call_id']}: "
                             f"{ctx['n_turns']} turns, {len(ctx['contacts'])} contacts, "
                             f"{len(ctx['deals'])} deal(s).",
                  "metadata": {"n_records": ctx["n_turns"]}})
        except KeyError as e:
            emit_error(str(e))
    elif cmd == "pending":
        try:
            agent = params["agent"]
            ids = list_pending(agent, require_stage_a=params.get("require_stage_a"))
            emit({"results": {"agent": agent, "pending": ids, "n_pending": len(ids)},
                  "summary": f"{len(ids)} call(s) pending for {agent}.",
                  "metadata": {"n_records": len(ids)}})
        except KeyError as e:
            emit_error(str(e))
    else:
        emit_error("usage: context_loader.py [context|pending] '<json>'")


if __name__ == "__main__":
    _main()
