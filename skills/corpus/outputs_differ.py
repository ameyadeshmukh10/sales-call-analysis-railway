"""Diff two versions of a Stage C/D deliverable → a "what changed and why" note.

Compounding payoff: when a new month of calls shifts the corpus, this names the
concrete deltas (new/dropped findings, percentage shifts, rank changes) between
v(N-1) and vN, writes `v<N>.diff.md`, and returns the markdown so the caller can
prepend it to the new deliverable as its changelog.

Findings are matched across versions by a normalized `claim` string; numeric
support (`pct`, `n_calls`) shifts are reported.

CLI:
  python -m skills.corpus.outputs_differ '{"deliverable":"discovery_playbook","to_v":2}'
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from skills.common.io_contract import OUTPUTS_DIR, emit, emit_error, read_params


def _load(deliverable: str, v: int) -> dict | None:
    p = OUTPUTS_DIR / deliverable / f"v{v}.json"
    return json.loads(p.read_text()) if p.exists() else None


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())[:120]


def _index(data: dict) -> dict[str, dict]:
    out = {}
    for f in (data or {}).get("findings", []):
        claim = f.get("claim") if isinstance(f, dict) else str(f)
        out[_norm(claim)] = f if isinstance(f, dict) else {"claim": claim}
    return out


def _support_pct(f: dict):
    sup = f.get("support") or {}
    return sup.get("pct")


def _sections_changelog(old: dict, new: dict, to_v: int, from_v: int) -> str:
    """Diff section-shaped (script) deliverables by heading."""
    oh = {(_norm(s.get("heading", ""))): s for s in old.get("sections", [])}
    nh = {(_norm(s.get("heading", ""))): s for s in new.get("sections", [])}
    added = [nh[k].get("heading") for k in nh if k not in oh]
    dropped = [oh[k].get("heading") for k in oh if k not in nh]
    changed = [nh[k].get("heading") for k in nh if k in oh
               and _norm(nh[k].get("talk_track", "")) != _norm(oh[k].get("talk_track", ""))]
    lines = [f"## Changelog — v{to_v} (vs v{from_v})\n"]
    if added:
        lines.append("**New sections:** " + ", ".join(added))
    if dropped:
        lines.append("**Removed sections:** " + ", ".join(dropped))
    if changed:
        lines.append(f"**Reworded ({len(changed)}):** " + ", ".join(changed[:8]))
    if not (added or dropped or changed):
        lines.append("_No section-level changes vs the prior version._")
    return "\n".join(lines) + "\n"


def diff_outputs(deliverable: str, to_v: int, from_v: int | None = None) -> str:
    from_v = from_v if from_v is not None else to_v - 1
    new = _load(deliverable, to_v) or {}
    old = _load(deliverable, from_v) if from_v >= 1 else None

    # script-shaped deliverables (sections, no findings) diff by section heading
    if old is not None and new.get("sections") and not new.get("findings"):
        md = _sections_changelog(old, new, to_v, from_v)
        (OUTPUTS_DIR / deliverable / f"v{to_v}.diff.md").write_text(md)
        return md

    if old is None:
        if new.get("findings"):
            base = f"{len(new['findings'])} findings"
        elif new.get("sections"):
            base = f"{len(new['sections'])} sections"
        else:
            base = "baseline content"
        md = (f"## Changelog — v{to_v}\n\n"
              f"First version of **{deliverable}**. No prior version to compare. "
              f"{base} established as the baseline.\n")
        (OUTPUTS_DIR / deliverable / f"v{to_v}.diff.md").write_text(md)
        return md

    oi, ni = _index(old), _index(new)
    added = [ni[k] for k in ni if k not in oi]
    dropped = [oi[k] for k in oi if k not in ni]
    shifted = []
    for k in ni:
        if k in oi:
            np_, op = _support_pct(ni[k]), _support_pct(oi[k])
            if np_ is not None and op is not None and abs(np_ - op) >= 5:
                shifted.append((ni[k].get("claim"), op, np_))

    lines = [f"## Changelog — v{to_v} (vs v{from_v})\n"]
    if added:
        lines.append(f"**New findings ({len(added)}):**")
        lines += [f"- {f.get('claim')}" + (f" — {_support_pct(f)}% of calls" if _support_pct(f) is not None else "")
                  for f in added]
        lines.append("")
    if dropped:
        lines.append(f"**No longer surfaced ({len(dropped)}):**")
        lines += [f"- {f.get('claim')}" for f in dropped]
        lines.append("")
    if shifted:
        lines.append("**Support shifted (≥5 pts):**")
        lines += [f"- {claim}: {op}% → {np_}%" for claim, op, np_ in shifted]
        lines.append("")
    if not (added or dropped or shifted):
        lines.append("_No material changes in findings vs the prior version._")
    md = "\n".join(lines) + "\n"
    (OUTPUTS_DIR / deliverable / f"v{to_v}.diff.md").write_text(md)
    return md


if __name__ == "__main__":
    p = read_params()
    try:
        md = diff_outputs(p["deliverable"], int(p["to_v"]), p.get("from_v"))
        emit({"results": {"diff_md": md},
              "summary": f"Diffed {p['deliverable']} v{p['to_v']}.",
              "metadata": {"n_records": 1}})
    except KeyError as e:
        emit_error(f"missing param: {e}")
