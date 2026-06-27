# Workflows — how the analysis layer runs

The analysis layer runs as **native Claude Code subagents** dispatched by the
`call-analysis-orchestrator` (or invoked individually). The deterministic skills
in `skills/` load context and persist results; the agents do the reasoning. No
LLM API key is required — it runs in your Claude Code session.

## The A → B → C → D sequence

```
Stage A (per call)   speaker_attribution  ──┐  (GATE: must run first)
                     rep_talk_extraction    │
                     customer_voice_extraction
                                             ▼
Stage B (per call)   discovery_quality, objection_handling,
                     pricing_packaging_reaction, call_structure,
                     competitive_mention, commitment_next_step, icp_fit_tagger
                                             ▼
Stage C (corpus)     performance_scorer (deterministic) → best_performing_call
                     → rubric_derivation                 → outputs/rubric/vN
                                             ▼
Stage D (corpus)     pricing_packaging_insights, discovery_playbook,
                     sales_call_sequence_script          → outputs/<deliverable>/vN
```

**Currently built: Stage A** + the deterministic skill spine. Stage B/C/D are
designed and registered (`built: False` in the registry) for the next phase.

## How the orchestrator runs (idempotent + resumable)

For each agent in stage order:
1. `python -m skills.store_io.context_loader pending '{"agent":"<agent>"}'`
   → the list of call_ids still needing it (already encodes the Stage-A gate).
2. For each pending call: load context, dispatch the agent subagent with that
   context, receive strict JSON, and persist via `results_io write`.
3. Re-running the orchestrator processes only what's still pending → **zero
   rework** on completed calls; failures are naturally retried next pass.

The Stage-A gate is automatic: `list_pending('discovery_quality')` returns `[]`
until a call has a current `speaker_attribution` result, so Stage B can't run
ahead of Stage A.

## Compounding across months

When June's calls are ingested (Part 1, incremental) and transcribed, re-running
the orchestrator picks them up via the worklist and extends every per-call
result set. Stage C/D then produce a new `outputs/<deliverable>/v<N+1>` with a
`v<N+1>.diff.md` describing what changed vs the prior version and why. Prior
versions are never deleted — the trajectory is the product.

## Dispatch model & cost
~61 calls × 7 per-call agents ≈ 427 subagent invocations for a full Stage A+B
pass, dispatched in waves via the Task tool. No per-call API cost (runs on your
Claude Code session). Narrow extractors use a fast model; rubric/synthesis use a
stronger one (set per-agent in the agent frontmatter).
