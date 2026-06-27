"""Validate + persist agent results to the versioned `analysis_results` store.

Thin deterministic layer over `pipeline.store`. The agents emit JSON; this skill
is the strict-JSON gate that keeps native-subagent output trustworthy: it checks
the result has the agent's required keys, stamps it with the current
prompt_version + a write timestamp, then appends it via
`store.write_analysis` (which keeps prior versions — compounding).

CLI:
  python -m skills.store_io.results_io write '{"call_id":"...","agent":"...","result":{...}}'
  python -m skills.store_io.results_io read  '{"call_id":"...","agent":"..."}'
"""
from __future__ import annotations

import sys
from typing import Any

# allow `python -m skills.store_io.results_io`
from pipeline import store
from skills.common.io_contract import emit, emit_error, read_params
from skills.store_io import registry


def validate(result: Any, agent: str) -> tuple[bool, list[str]]:
    """Presence/shape gate. Returns (ok, errors)."""
    errors: list[str] = []
    if not registry.is_known(agent):
        return False, [f"unknown agent '{agent}'"]
    if not isinstance(result, dict):
        return False, ["result must be a JSON object"]
    for key in registry.required_keys(agent):
        if key not in result:
            errors.append(f"missing required key '{key}'")
    sv = result.get("schema_version")
    if registry.required_keys(agent) and sv in (None, ""):
        errors.append("schema_version must be set")
    return (len(errors) == 0), errors


def write_result(call_id: str, agent: str, result: dict) -> int:
    """Validate, stamp, and append a versioned result. Returns the store version.

    Raises ValueError on validation failure so a bad agent emission is never
    silently stored.
    """
    ok, errors = validate(result, agent)
    if not ok:
        raise ValueError(f"validation failed for {agent}/{call_id}: {errors}")
    stamped = dict(result)
    stamped["_prompt_version"] = registry.prompt_version(agent)
    stamped["_written_at"] = store.now_iso()
    with store.connect() as conn:
        return store.write_analysis(conn, call_id, agent, stamped)


def read_latest(call_id: str, agent: str) -> dict | None:
    with store.connect() as conn:
        return store.latest_analysis(conn, call_id, agent)


def read_all_for_agent(agent: str) -> list[tuple[str, dict]]:
    """All calls' latest result for an agent: [(call_id, result), ...]."""
    out: list[tuple[str, dict]] = []
    with store.connect() as conn:
        rows = conn.execute(
            "SELECT DISTINCT call_id FROM analysis_results WHERE agent=?",
            (agent,)).fetchall()
        for r in rows:
            res = store.latest_analysis(conn, r["call_id"], agent)
            if res is not None:
                out.append((r["call_id"], res))
    return out


# ---------------- CLI ---------------- #

def _main() -> None:
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    # params come from argv[2] or stdin
    if len(sys.argv) > 2:
        sys.argv = [sys.argv[0], sys.argv[2]]
    else:
        sys.argv = [sys.argv[0]]
    params = read_params()

    if cmd == "write":
        try:
            v = write_result(params["call_id"], params["agent"], params["result"])
            emit({"results": {"call_id": params["call_id"], "agent": params["agent"],
                              "version": v},
                  "summary": f"Wrote {params['agent']} result for {params['call_id']} "
                             f"as version {v}.",
                  "metadata": {"n_records": 1}})
        except (KeyError, ValueError) as e:
            emit_error(str(e))
    elif cmd == "read":
        res = read_latest(params["call_id"], params["agent"])
        emit({"results": res,
              "summary": ("Found result." if res else "No result stored."),
              "metadata": {"n_records": 1 if res else 0}})
    else:
        emit_error("usage: results_io.py [write|read] '<json>'")


if __name__ == "__main__":
    _main()
