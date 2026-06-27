"""Compile the Stage C/D deliverables into a single ranked action-item list.

Deterministic — it COMPILES, it does not reason. Reads each deliverable's latest
`vN.json` (recommendations + findings) plus the corpus aggregate, turns each
recommendation / anti-pattern into an action item, attaches its strongest
supporting finding (for the stat + example calls), and ranks by
`priority_score = 0.6*reach + 0.4*severity`.

Writes a versioned deliverable to `outputs/action_items/vN.json` via the existing
`outputs_versioner`, so it versions + keeps a `latest` like every other output.

CLI:  python -m skills.corpus.action_items
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

from skills.common.io_contract import OUTPUTS_DIR, emit
from skills.corpus import outputs_versioner

DATA_DIR = Path(os.environ.get("DATA_DIR", "./data")).resolve()

# deliverable dir -> (friendly source label, base severity 0..1)
SOURCES = {
    "pricing_packaging_insights": ("Pricing & Packaging", 0.95),
    "sales_call_sequence_script": ("Call Sequence", 0.85),
    "discovery_playbook": ("Discovery", 0.70),
    "rubric": ("Rubric", 0.60),
}


def _latest_json(deliverable: str) -> dict:
    d = OUTPUTS_DIR / deliverable
    vs = sorted(int(p.stem[1:]) for p in d.glob("v*.json")
                if p.stem[1:].isdigit()) if d.exists() else []
    if not vs:
        return {}
    return json.loads((d / f"v{vs[-1]}.json").read_text())


def _findings(data: dict) -> list[dict]:
    out = []
    for f in data.get("findings", []) or []:
        if isinstance(f, dict):
            sup = f.get("support") or {}
            out.append({"claim": f.get("claim", ""),
                        "pct": sup.get("pct"), "n_calls": sup.get("n_calls"),
                        "example_calls": sup.get("example_calls", [])})
    return out


def _best_support(findings: list[dict], text: str) -> dict:
    """Pick the finding whose claim genuinely overlaps the recommendation text.
    Require a real word-overlap; otherwise attach no stat (don't paste the same
    top finding onto every recommendation)."""
    stop = {"with", "that", "this", "from", "your", "into", "have", "they",
            "them", "when", "what", "which", "their", "more", "than", "call",
            "calls", "reps", "rep", "pricing", "model"}
    words = set(re.findall(r"[a-z]{4,}", text.lower())) - stop
    best, best_overlap = None, 0
    for f in findings:
        fw = set(re.findall(r"[a-z]{4,}", (f["claim"] or "").lower())) - stop
        overlap = len(words & fw)
        if overlap > best_overlap:
            best, best_overlap = f, overlap
    if best is None or best_overlap < 2:   # too weak a match -> no borrowed stat
        return {"pct": None, "n_calls": None, "example_calls": []}
    return best


def compile_action_items() -> dict:
    items = []
    counter = {}
    for deliverable, (label, severity) in SOURCES.items():
        data = _latest_json(deliverable)
        if not data:
            continue
        findings = _findings(data)
        # recommendations (Stage D) -> items
        for rec in data.get("recommendations", []) or []:
            sup = _best_support(findings, rec)
            counter[deliverable] = counter.get(deliverable, 0) + 1
            reach = (sup.get("pct") or 0) / 100.0
            items.append({
                "id": f"{deliverable[:4]}-{counter[deliverable]:02d}",
                "title": rec if len(rec) < 160 else rec[:157] + "…",
                "detail": rec,
                "source_deliverable": deliverable,
                "source_label": label,
                "source_kind": "recommendation",
                "supporting_stat": {"n_calls": sup.get("n_calls"), "pct": sup.get("pct")},
                "example_calls": (sup.get("example_calls") or [])[:6],
                "priority_score": round(100 * (0.6 * reach + 0.4 * severity), 1),
            })
        # rubric anti_patterns -> items
        for ap in data.get("anti_patterns", []) or []:
            if not isinstance(ap, dict):
                continue
            counter[deliverable] = counter.get(deliverable, 0) + 1
            items.append({
                "id": f"{deliverable[:4]}-{counter[deliverable]:02d}",
                "title": f"Eliminate anti-pattern: {ap.get('pattern','')}"[:160],
                "detail": ap.get("pattern", ""),
                "source_deliverable": deliverable,
                "source_label": label,
                "source_kind": "anti_pattern",
                "supporting_stat": {"n_calls": len(ap.get("from_calls", []) or []), "pct": None},
                "example_calls": (ap.get("from_calls") or [])[:6],
                "priority_score": round(100 * (0.6 * 0.4 + 0.4 * severity), 1),
            })

    items.sort(key=lambda x: x["priority_score"], reverse=True)
    if items:
        hi = items[0]["priority_score"]
        lo = items[-1]["priority_score"]
        cut_hi = lo + (hi - lo) * 2 / 3
        cut_md = lo + (hi - lo) * 1 / 3
        for it in items:
            it["priority"] = ("high" if it["priority_score"] >= cut_hi
                              else "medium" if it["priority_score"] >= cut_md else "low")

    result = {"schema_version": "1.0", "n_items": len(items), "items": items}
    md = _render_md(result)
    out = outputs_versioner.write_output("action_items", md=md, data=result)
    result["_artifact"] = out
    return result


def _render_md(result: dict) -> str:
    lines = ["# Action Items — compiled from the corpus deliverables\n",
             f"_{result['n_items']} items, ranked by reach × severity._\n"]
    for it in result["items"]:
        stat = it["supporting_stat"]
        s = f" ({stat['pct']:.0f}% of calls, n={stat['n_calls']})" if stat.get("pct") else (
            f" (n={stat['n_calls']} calls)" if stat.get("n_calls") else "")
        lines.append(f"### [{it.get('priority','').upper()}] {it['title']}")
        lines.append(f"*{it['source_label']} · score {it['priority_score']}*{s}")
        if it.get("example_calls"):
            lines.append(f"Example calls: {', '.join(it['example_calls'][:6])}")
        lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    r = compile_action_items()
    top = r["items"][:5]
    emit({"results": {"n_items": r["n_items"],
                      "top": [(t["priority"], t["priority_score"], t["title"][:70]) for t in top],
                      "version": r.get("_artifact", {}).get("version")},
          "summary": f"Compiled {r['n_items']} action items into "
                     f"outputs/action_items/v{r.get('_artifact',{}).get('version')}.",
          "metadata": {"n_records": r["n_items"]}})
