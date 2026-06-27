"""Roll per-call Stage A/B results into corpus-level tallies for Stage D agents.

Deterministic. Produces counts + percentages + example call_ids so a Stage D
synthesis agent can make supported, cited claims instead of re-reading 61
transcripts. Also emits compact per-call summaries the agent can scan.

CLI:  python -m skills.corpus.corpus_aggregator
"""
from __future__ import annotations

from collections import Counter, defaultdict

from pipeline import store
from skills.common.io_contract import emit, write_json, DATA_DIR
from skills.store_io import results_io


def _present_calls() -> list[str]:
    with store.connect() as conn:
        return [r["call_id"] for r in conn.execute(
            "SELECT call_id FROM calls WHERE transcript_status='present' "
            "ORDER BY hs_timestamp")]


def _pct(n: int, d: int) -> float:
    return round(100 * n / d, 1) if d else 0.0


def aggregate() -> dict:
    calls = _present_calls()
    n = len(calls)
    latest = {a: dict(results_io.read_all_for_agent(a)) for a in [
        "speaker_attribution", "rep_talk_extraction", "customer_voice_extraction",
        "discovery_quality", "objection_handling", "pricing_packaging_reaction",
        "call_structure", "competitive_mention", "commitment_next_step",
        "icp_fit_tagger"]}

    obj_families = Counter()
    obj_examples = defaultdict(list)
    tiers = Counter()
    pricing_discussed = 0
    price_objection = 0
    reaction = Counter()
    bundling_examples = []
    competitors = Counter()
    comp_examples = defaultdict(list)
    next_step_secured = 0
    next_step_types = Counter()
    disc_scores = []
    seq_followed = 0
    ttfdq = []
    icp_tiers = Counter()
    personas = Counter()
    per_call = []

    for cid in calls:
        oh = latest["objection_handling"].get(cid)
        if oh:
            for o in oh.get("objections", []):
                fam = o.get("family", "other")
                obj_families[fam] += 1
                if len(obj_examples[fam]) < 6:
                    obj_examples[fam].append({"call_id": cid, "label": o.get("label"),
                                              "turn": o.get("raised_turn")})
        pr = latest["pricing_packaging_reaction"].get(cid)
        if pr:
            if pr.get("pricing_discussed"):
                pricing_discussed += 1
            if pr.get("price_objection"):
                price_objection += 1
            for t in pr.get("tiers_mentioned", []) or []:
                tiers[t] += 1
            reaction[pr.get("buyer_reaction", "none")] += 1
            for b in pr.get("bundling_signals", []) or []:
                if len(bundling_examples) < 12:
                    bundling_examples.append({"call_id": cid, "signal": b})
        cm = latest["competitive_mention"].get(cid)
        if cm:
            for c in cm.get("competitors", []):
                nm = (c.get("name") or "").strip()
                if nm:
                    competitors[nm] += 1
                    if len(comp_examples[nm]) < 6:
                        comp_examples[nm].append({"call_id": cid, "turn": c.get("turn"),
                                                  "sentiment": c.get("sentiment")})
        ns = latest["commitment_next_step"].get(cid)
        if ns:
            if ns.get("next_step_secured"):
                next_step_secured += 1
            next_step_types[ns.get("next_step_type", "none")] += 1
        dq = latest["discovery_quality"].get(cid)
        if dq and dq.get("score") is not None:
            disc_scores.append({"call_id": cid, "score": dq.get("score")})
        cs = latest["call_structure"].get(cid)
        if cs:
            if cs.get("followed_expected_sequence"):
                seq_followed += 1
            if cs.get("time_to_first_discovery_q") is not None:
                ttfdq.append(cs.get("time_to_first_discovery_q"))
        ic = latest["icp_fit_tagger"].get(cid)
        if ic:
            icp_tiers[str(ic.get("icp_tier"))] += 1
            personas[ic.get("persona_family", "Other")] += 1

        per_call.append({
            "call_id": cid,
            "discovery_score": (dq or {}).get("score"),
            "n_objections": (oh or {}).get("n_objections"),
            "pricing_discussed": (pr or {}).get("pricing_discussed"),
            "next_step_secured": (ns or {}).get("next_step_secured"),
            "icp_tier": (ic or {}).get("icp_tier"),
            "persona": (ic or {}).get("persona_family"),
        })

    coverage = {a: len(latest[a]) for a in latest}
    result = {
        "n_calls": n,
        "coverage": coverage,
        "objection_families": {k: {"n": v, "pct": _pct(v, sum(obj_families.values())),
                                   "examples": obj_examples[k]}
                               for k, v in obj_families.most_common()},
        "pricing": {
            "discussed_n": pricing_discussed, "discussed_pct": _pct(pricing_discussed, coverage["pricing_packaging_reaction"] or n),
            "price_objection_n": price_objection,
            "tiers_mentioned": dict(tiers),
            "buyer_reaction": dict(reaction),
            "bundling_signals": bundling_examples,
        },
        "competitors": {k: {"n": v, "examples": comp_examples[k]}
                        for k, v in competitors.most_common()},
        "next_step": {"secured_n": next_step_secured,
                      "secured_pct": _pct(next_step_secured, coverage["commitment_next_step"] or n),
                      "types": dict(next_step_types)},
        "discovery": {"scores": disc_scores,
                      "mean": round(sum(d["score"] for d in disc_scores) / len(disc_scores), 1) if disc_scores else None},
        "call_structure": {"followed_expected_pct": _pct(seq_followed, coverage["call_structure"] or n),
                           "mean_time_to_first_discovery_q": round(sum(ttfdq) / len(ttfdq), 1) if ttfdq else None},
        "icp": {"tiers": dict(icp_tiers), "personas": dict(personas)},
        "per_call": per_call,
    }
    path = write_json(DATA_DIR / "results" / "corpus_aggregate.json", result)
    result["_artifact"] = str(path)
    return result


if __name__ == "__main__":
    r = aggregate()
    emit({"results": {k: v for k, v in r.items() if k not in ("per_call",)},
          "summary": f"Aggregated {r['n_calls']} calls. Coverage: {r['coverage']}.",
          "metadata": {"n_records": r["n_calls"], "artifacts": {"json": r.get("_artifact")}}})
