# Skills Reference — deterministic I/O for agents

These are **deterministic** Python skills (no LLM calls). Agents invoke them to
load context and persist validated results. Each prints a JSON envelope
`{results, summary, metadata}` to stdout. Params are passed as a JSON string
argument or via stdin.

## context_loader — load per-call context + the worklist

```bash
# Full context for one call (participants, firmographics, deal, indexed turns)
python -m skills.store_io.context_loader context '{"call_id":"489376191737"}'

# Which calls still need an agent (resumable worklist + dependency gate)
python -m skills.store_io.context_loader pending '{"agent":"speaker_attribution"}'
python -m skills.store_io.context_loader pending '{"agent":"discovery_quality"}'
```

`load_call_context(call_id)` returns: `rep` (name/email from owner), `contacts`
(name + job_title — the customer-side anchors), `companies` (firmographics),
`deals` (stage_label/status/amount/is_won), and `turns` (each `{i, text,
start_ms, end_ms}`). The integer `i` is the citation index agents must use.

`list_pending(agent)` returns only calls that (a) have a transcript, (b) lack a
current-`prompt_version` result for the agent, and (c) satisfy the agent's
prerequisites (`registry.requires`). This is what makes re-runs idempotent and
enforces the Stage-A gate.

## results_io — validate + persist agent output

```bash
# Write a validated, versioned result
python -m skills.store_io.results_io write \
  '{"call_id":"489376191737","agent":"speaker_attribution","result":{...}}'

# Read the latest stored result
python -m skills.store_io.results_io read \
  '{"call_id":"489376191737","agent":"speaker_attribution"}'
```

`write_result` validates the result against the agent's `required_keys`
(`skills/store_io/registry.py`), stamps `_prompt_version` + `_written_at`, and
appends a new version via `store.write_analysis`. It **raises** on malformed
output — a bad emission is never silently stored.

## registry — the agent catalog (single source of truth)

`skills/store_io/registry.py` holds each agent's `stage`, `prompt_version`,
`required_keys`, `requires` (dependencies), and `built` flag. Bump
`prompt_version` when you change an agent's logic to trigger a clean recompute.

## Skills built next phase
`skills/corpus/`: `performance_scorer` (Stage C composite), `corpus_aggregator`
(Stage D tallies), `outputs_versioner` + `outputs_differ` (versioned deliverables
with diffs). Designed in the plan; not yet implemented.
