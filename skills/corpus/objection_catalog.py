"""Deterministic objection catalog — the gather step for objection intelligence.

Joins every catalogued objection (objection_handling) to its verbatim buyer quote
(customer_voice_extraction, by turn) plus the call's company and deal outcome, and
rolls it up per family. Writes data/results/objection_catalog.json, which feeds
both the Objections UI page and the `objection-analysis` LLM agent (which clusters
the instances into named sub-types).

No LLM here — pure aggregation. CLI:  python -m skills.corpus.objection_catalog
"""
from __future__ import annotations

from collections import Counter

from pipeline import store
from skills.common.io_contract import emit, write_json, DATA_DIR
from skills.store_io import results_io, registry

FAMILIES = ["fit", "risk", "price", "quality", "other"]


def _present_calls() -> list[str]:
    with store.connect() as conn:
        return [r["call_id"] for r in conn.execute(
            "SELECT call_id FROM calls WHERE transcript_status='present' "
            "ORDER BY hs_timestamp")]


def _pct(n: int, d: int) -> float:
    return round(100 * n / d, 1) if d else 0.0


def _verbatim_index(cv_result: dict | None) -> dict[int, str]:
    """objections_raised -> {turn_i: verbatim text}."""
    out: dict[int, str] = {}
    for o in (cv_result or {}).get("objections_raised", []) or []:
        i = o.get("i")
        if isinstance(i, int):
            out[i] = o.get("text", "")
    return out


def _match_verbatim(turn, vindex: dict[int, str]) -> str:
    """Exact i==raised_turn, else nearest within +/-3 turns, else ''."""
    if turn is None or not vindex:
        return ""
    if turn in vindex:
        return vindex[turn]
    best, best_d = "", 4
    for i, txt in vindex.items():
        d = abs(i - turn)
        if d < best_d:
            best, best_d = txt, d
    return best


def _company_map() -> dict[str, str]:
    out: dict[str, str] = {}
    with store.connect() as conn:
        for r in conn.execute("SELECT call_id FROM calls WHERE transcript_status='present'"):
            cid = r["call_id"]
            row = conn.execute(
                "SELECT co.name FROM companies co JOIN call_companies cc "
                "ON cc.company_id=co.company_id WHERE cc.call_id=? AND co.name!='EverWorker' "
                "LIMIT 1", (cid,)).fetchone()
            out[cid] = row["name"] if row else None
    return out


def _deal_outcome_map() -> dict[str, dict]:
    """call_id -> {deal_status, composite_score} for the outcome lean."""
    out: dict[str, dict] = {}
    with store.connect() as conn:
        ranking = store.latest_analysis(conn, registry.CORPUS_ID, "best_performing_call") or {}
        comp = {r["call_id"]: r.get("composite_score") for r in ranking.get("ranked", [])}
        for r in conn.execute("SELECT call_id FROM calls WHERE transcript_status='present'"):
            cid = r["call_id"]
            d = conn.execute(
                "SELECT d.status FROM deals d JOIN call_deals cd ON cd.deal_id=d.deal_id "
                "WHERE cd.call_id=? LIMIT 1", (cid,)).fetchone()
            out[cid] = {"deal_status": d["status"] if d else "no_deal",
                        "composite_score": comp.get(cid)}
    return out


def build_catalog() -> dict:
    calls = _present_calls()
    oh = dict(results_io.read_all_for_agent("objection_handling"))
    cv = dict(results_io.read_all_for_agent("customer_voice_extraction"))
    comp = _company_map()
    outcomes = _deal_outcome_map()

    fams: dict[str, dict] = {f: {"instances": []} for f in FAMILIES}
    n_objections = 0
    for cid in calls:
        vindex = _verbatim_index(cv.get(cid))
        oc = outcomes.get(cid, {})
        for o in (oh.get(cid) or {}).get("objections", []) or []:
            fam = o.get("family") if o.get("family") in FAMILIES else "other"
            hq = o.get("handling_quality")
            inst = {
                "call_id": cid, "company": comp.get(cid),
                "family": fam, "label": o.get("label", ""),
                "verbatim": _match_verbatim(o.get("raised_turn"), vindex),
                "turn": o.get("raised_turn"),
                "technique": o.get("technique"),
                "handling_quality": hq, "handled": bool(o.get("handled")),
                "response_summary": o.get("response_summary", ""),
                "deal_status": oc.get("deal_status"),
                "composite_score": oc.get("composite_score"),
            }
            fams[fam]["instances"].append(inst)
            n_objections += 1

    # per-family rollups
    overall_tech, overall_hq = Counter(), Counter()
    overall_resolved = 0
    for fam, fc in fams.items():
        insts = fc["instances"]
        n = len(insts)
        resolved = sum(1 for i in insts if i["handled"] and (i["handling_quality"] or 0) >= 2)
        handled = sum(1 for i in insts if i["handled"])
        tech = Counter(i["technique"] for i in insts if i["technique"])
        hq = Counter(str(i["handling_quality"]) for i in insts if i["handling_quality"] is not None)
        overall_tech.update(tech)
        overall_hq.update(hq)
        overall_resolved += resolved
        # examples: resolved first (for "best handled" material), then the rest
        ex = sorted(insts, key=lambda i: (not (i["handled"] and (i["handling_quality"] or 0) >= 2)))
        fc.update({
            "n": n, "pct": _pct(n, n_objections),
            "resolved_n": resolved, "resolved_rate": _pct(resolved, n),
            "handled_pct": _pct(handled, n),
            "technique_dist": dict(tech), "handling_quality_dist": dict(hq),
            "top_example_calls": [{"call_id": i["call_id"], "company": i["company"],
                                   "label": i["label"], "turn": i["turn"]} for i in ex[:6]],
        })

    result = {
        "n_calls": len(calls), "n_objections": n_objections,
        "families": fams,
        "overall": {"resolved_rate": _pct(overall_resolved, n_objections),
                    "technique_dist": dict(overall_tech),
                    "handling_quality_dist": dict(overall_hq)},
    }
    path = write_json(DATA_DIR / "results" / "objection_catalog.json", result)
    result["_artifact"] = str(path)
    return result


if __name__ == "__main__":
    r = build_catalog()
    fam_counts = {f: r["families"][f]["n"] for f in FAMILIES if r["families"][f]["n"]}
    emit({"results": {"n_objections": r["n_objections"], "n_calls": r["n_calls"],
                      "by_family": fam_counts, "overall_resolved_rate": r["overall"]["resolved_rate"]},
          "summary": f"Cataloged {r['n_objections']} objections across "
                     f"{len(fam_counts)} families ({r['overall']['resolved_rate']}% resolved).",
          "metadata": {"n_records": r["n_objections"], "artifacts": {"json": r.get("_artifact")}}})
