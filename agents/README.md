# Analysis Agents

The full, human-readable logic for every analysis agent lives **here** (visible,
not hidden). Each `.claude/agents/<name>.md` is a thin Claude Code trigger-wrapper
that points back to the matching file in this folder — so the agents are
discoverable/dispatchable by Claude Code while the real content stays in plain
sight and is the single source of truth.

These agents do **judgment work** (LLM reasoning over transcripts). The
deterministic plumbing they call — loading call context, validating + persisting
results — lives in `skills/`. The shared rules every agent obeys are in
`docs/analysis_rules.md`; the taxonomy/pricing/persona grounding is in
`docs/interpretation.md`.

## The A → B → C → D map

| Stage | Agent | Purpose | Built |
|---|---|---|---|
| — | **call-analysis-orchestrator** | entry point; sequences the stages, enforces the Stage-A gate, resumable | ✅ |
| A | **speaker-attribution** | label every turn rep-vs-customer (the gate) | ✅ |
| A | **rep-talk-extraction** | rep's questions, pitch claims, framing moves | ✅ |
| A | **customer-voice-extraction** | buyer's pains, goals, objections, signals — verbatim | ✅ |
| B | discovery-quality | score discovery rigor | ✅ |
| B | objection-handling | catalog objections (quality/risk/fit/price) + handling | ✅ |
| B | pricing-packaging-reaction | pricing/packaging moments + buyer reaction | ✅ |
| B | call-structure | segment the call into phases; assess sequence | ✅ |
| B | competitive-mention | competitor references + positioning | ✅ |
| B | commitment-next-step | the concrete forward commitment | ✅ |
| B | icp-fit-tagger | tag the account against ICP | ✅ |
| C | best-performing-call | rank calls by composite performance score (deterministic) | ✅ |
| C | rubric-derivation | derive OUR winning-call rubric from top calls | ✅ |
| D | pricing-packaging-insights | corpus pricing/packaging recommendations | ✅ |
| D | discovery-playbook | the reusable discovery question playbook | ✅ |
| D | sales-call-sequence-script | the ideal call flow/script | ✅ |

## Running them
Invoke the **call-analysis-orchestrator** for a full pass, or a single specialist
for one call. See `docs/workflows.md`. No API key needed — runs in your Claude
Code session; results are versioned in `data/calls.db` (`analysis_results`) and,
for Stage C/D, in `outputs/`.
