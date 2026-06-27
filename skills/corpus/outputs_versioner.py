"""Write versioned Stage C/D deliverables to outputs/<deliverable>/v<N>.{md,json}.

Never overwrites: each run is a new version, priors retained, a `latest.md`
pointer updated. Compounding lives here — `outputs_differ` then explains what
changed vs the prior version.

CLI:
  python -m skills.corpus.outputs_versioner write \
    '{"deliverable":"discovery_playbook","md":"# ...","data":{...}}'
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from skills.common.io_contract import OUTPUTS_DIR, emit, emit_error, read_params


def _dir(deliverable: str) -> Path:
    d = OUTPUTS_DIR / deliverable
    d.mkdir(parents=True, exist_ok=True)
    return d


def next_output_version(deliverable: str) -> int:
    d = _dir(deliverable)
    vs = [int(m.group(1)) for p in d.glob("v*.json")
          if (m := re.match(r"v(\d+)\.json$", p.name))]
    return (max(vs) + 1) if vs else 1


def write_output(deliverable: str, *, md: str, data: dict) -> dict:
    d = _dir(deliverable)
    v = next_output_version(deliverable)
    md_path = d / f"v{v}.md"
    json_path = d / f"v{v}.json"
    md_path.write_text(md)
    json_path.write_text(json.dumps(data, default=str, indent=2))
    (d / "latest.md").write_text(f"See v{v}.md (newest). All versions retained.\n\n{md}")
    return {"deliverable": deliverable, "version": v,
            "md": str(md_path), "json": str(json_path)}


def _main() -> None:
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if len(sys.argv) > 2:
        sys.argv = [sys.argv[0], sys.argv[2]]
    else:
        sys.argv = [sys.argv[0]]
    params = read_params()
    if cmd == "write":
        try:
            r = write_output(params["deliverable"], md=params["md"], data=params["data"])
            emit({"results": r,
                  "summary": f"Wrote {params['deliverable']} v{r['version']}.",
                  "metadata": {"n_records": 1, "artifacts": {"md": r["md"], "json": r["json"]}}})
        except KeyError as e:
            emit_error(f"missing param: {e}")
    elif cmd == "next":
        emit({"results": {"next_version": next_output_version(params["deliverable"])},
              "summary": "ok", "metadata": {"n_records": 1}})
    else:
        emit_error("usage: outputs_versioner.py [write|next] '<json>'")


if __name__ == "__main__":
    _main()
