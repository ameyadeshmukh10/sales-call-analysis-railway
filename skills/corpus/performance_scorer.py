"""Deterministic composite performance score for every call (Stage C engine).

Won/lost alone is unusable (only 2 won deals). This computes a transparent,
additive 0-100 composite from store fields + Stage A/B results, so the ranking is
reproducible and auditable — NOT an LLM guess. Every component value is shown.

Components & default weights (also documented in docs/interpretation.md):
  stage_progression 0.35 · next_step 0.20 · amount_percentile 0.10 ·
  engagement 0.15 · discovery 0.10 · objection_handling 0.10

Missing components (an agent hasn't run for a call) are dropped and the remaining
weights renormalized, with `coverage` recording what was available — so partial
runs still produce a sane ranking.

Writes the ranked result under (CORPUS_ID, "best_performing_call") and returns it.

CLI:  python -m skills.corpus.performance_scorer
"""
from __future__ import annotations

from pipeline import store
from skills.common.io_contract import emit
from skills.store_io import registry
from skills.store_io import results_io

DEFAULT_WEIGHTS = {
    "stage_progression": 0.35,
    "next_step": 0.20,
    "amount_percentile": 0.10,
    "engagement": 0.15,
    "discovery": 0.10,
    "objection_handling": 0.10,
}

# Transparent stage -> progression score (0..1). Won=1, Lost=0.
STAGE_SCORE = [
    ("closed won", 1.00), ("closed lost", 0.00),
    ("stage 0", 0.15), ("stage 1", 0.30), ("stage 2", 0.50),
    ("stage 3", 0.65), ("stage 4", 0.80), ("stage 5", 0.90),
]

LIMITATION = (
    "Based on 61 calls from 2 reps with severely imbalanced outcomes "
    "(2 won / 14 lost / 31 open). Rankings are composite and process-based, not "
    "outcome-validated or causal. Treat as directional hypotheses to test as more "
    "calls arrive."
)


def _stage_progression(deals: list[dict]) -> float | None:
    if not deals:
        return None
    best = None
    for d in deals:
        lbl = (d.get("stage_label") or "").lower()
        sc = None
        if d.get("is_won"):
            sc = 1.0
        else:
            for key, val in STAGE_SCORE:
                if key in lbl:
                    sc = val
                    break
        if sc is not None:
            best = sc if best is None else max(best, sc)
    return best


def _percentiles(values: dict[str, float]) -> dict[str, float]:
    """Rank-percentile (0..1) for each key with a non-null value."""
    items = [(k, v) for k, v in values.items() if v is not None]
    if not items:
        return {}
    ordered = sorted(items, key=lambda kv: kv[1])
    n = len(ordered)
    out = {}
    for rank, (k, _) in enumerate(ordered):
        out[k] = rank / (n - 1) if n > 1 else 1.0
    return out


def score_corpus(weights: dict | None = None) -> dict:
    weights = weights or DEFAULT_WEIGHTS
    with store.connect() as conn:
        call_rows = conn.execute(
            "SELECT call_id FROM calls WHERE transcript_status='present' "
            "ORDER BY hs_timestamp").fetchall()
        call_ids = [r["call_id"] for r in call_rows]

    # gather raw signals per call
    raw: dict[str, dict] = {}
    amounts: dict[str, float] = {}
    with store.connect() as conn:
        for cid in call_ids:
            deals = []
            for r in conn.execute(
                    "SELECT d.stage_label, d.status, d.amount, d.is_won "
                    "FROM deals d JOIN call_deals cd ON cd.deal_id=d.deal_id "
                    "WHERE cd.call_id=?", (cid,)):
                deals.append(dict(r))
            sa = store.latest_analysis(conn, cid, "speaker_attribution")
            rep = store.latest_analysis(conn, cid, "rep_talk_extraction")
            cust = store.latest_analysis(conn, cid, "customer_voice_extraction")
            disc = store.latest_analysis(conn, cid, "discovery_quality")
            obj = store.latest_analysis(conn, cid, "objection_handling")
            nxt = store.latest_analysis(conn, cid, "commitment_next_step")

            amount = None
            for d in deals:
                if d.get("amount"):
                    amount = max(amount or 0, float(d["amount"]))
            amounts[cid] = amount

            n_turns = (sa or {}).get("n_rep_turns", 0) + (sa or {}).get("n_customer_turns", 0)
            engagement = None
            if cust and sa and n_turns:
                talk = cust.get("customer_talk_share")
                qdens = (rep.get("n_questions", 0) / n_turns) if rep else 0
                # balanced talk-share (~0.5 ideal) + question density
                bal = 1 - abs((talk if talk is not None else 0.5) - 0.5) * 2
                engagement = max(0.0, min(1.0, 0.6 * bal + 0.4 * min(qdens * 10, 1.0)))

            def _norm(d, key, denom):
                if not d:
                    return None
                v = d.get(key)
                return (v / denom) if isinstance(v, (int, float)) else None

            raw[cid] = {
                "deals": deals,
                "stage_progression": _stage_progression(deals),
                "next_step": _norm(nxt, "strength", 3.0),
                "engagement": engagement,
                "discovery": _norm(disc, "score", 100.0),
                "objection_handling": _norm(obj, "overall_handling", 100.0),
            }

    amt_pct = _percentiles(amounts)

    ranked = []
    with store.connect() as conn:
        for cid in call_ids:
            comps = dict(raw[cid])
            comps["amount_percentile"] = amt_pct.get(cid)
            present = {k: comps.get(k) for k in weights if comps.get(k) is not None}
            wsum = sum(weights[k] for k in present) or 1.0
            composite = round(100 * sum(weights[k] * present[k] for k in present) / wsum, 1)
            deals = raw[cid]["deals"]
            ranked.append({
                "call_id": cid,
                "composite_score": composite,
                "coverage": sorted(present.keys()),
                "components": {k: (round(comps[k], 3) if comps.get(k) is not None else None)
                              for k in weights},
                "deal_stage": deals[0]["stage_label"] if deals else None,
                "deal_status": deals[0]["status"] if deals else "no_deal",
            })
    ranked.sort(key=lambda r: r["composite_score"], reverse=True)
    top_k = [r["call_id"] for r in ranked[:8]]

    result = {
        "schema_version": "1.0",
        "weights": weights,
        "ranked": ranked,
        "top_k": top_k,
        "n_calls": len(ranked),
        "limitation_block": LIMITATION,
    }
    results_io.write_result(registry.CORPUS_ID, "best_performing_call", result)
    return result


if __name__ == "__main__":
    res = score_corpus()
    top = res["ranked"][:5]
    emit({"results": {"top_5": [(r["call_id"], r["composite_score"], r["deal_status"],
                                 r["coverage"]) for r in top], "n_calls": res["n_calls"]},
          "summary": f"Scored {res['n_calls']} calls. Top composite: "
                     f"{top[0]['composite_score'] if top else 'n/a'}. "
                     f"Stored under best_performing_call.",
          "metadata": {"n_records": res["n_calls"]}})
