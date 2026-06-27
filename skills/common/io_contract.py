"""Shared I/O contract for every analysis skill.

Mirrors the sibling GTM repo's contract so agents invoke skills the same way:

  1. accept params as a JSON string (argv[1]) OR via stdin
  2. write any large artifact under data/ or outputs/
  3. print a compact JSON envelope to stdout so the agent sees small context

Envelope:
  {
    "results":  <dict | list — the structured result>,
    "summary":  <2-3 sentence plain-English summary>,
    "metadata": {"n_records": int, "warnings": [str, ...], "artifacts": {...}}
  }

These skills are DETERMINISTIC plumbing — no LLM calls live here. The agents do
the reasoning; these skills load context and persist validated results.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

load_dotenv()

DATA_DIR = Path(os.environ.get("DATA_DIR", "./data")).resolve()
OUTPUTS_DIR = Path(os.environ.get("OUTPUTS_DIR", "./outputs")).resolve()
DATA_DIR.mkdir(parents=True, exist_ok=True)
OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)


def read_params() -> dict:
    """Read JSON params from argv[1] or stdin (empty dict if none)."""
    if len(sys.argv) > 1 and sys.argv[1].strip():
        raw = sys.argv[1]
    else:
        raw = sys.stdin.read() if not sys.stdin.isatty() else ""
    if not raw.strip():
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        emit_error(f"Invalid JSON params: {e}")
        sys.exit(2)


def emit(envelope: dict[str, Any]) -> None:
    """Print the envelope as compact JSON to stdout."""
    envelope.setdefault("metadata", {}).setdefault("warnings", [])
    print(json.dumps(envelope, default=str))


def emit_error(message: str, warnings: list[str] | None = None) -> None:
    emit({
        "results": None,
        "summary": f"ERROR: {message}",
        "metadata": {"n_records": 0, "warnings": warnings or [], "error": message},
    })


def hash_key(obj: Any, length: int = 10) -> str:
    payload = json.dumps(obj, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode()).hexdigest()[:length]


def write_json(path: Path | str, obj: Any) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, default=str, indent=2))
    return path
