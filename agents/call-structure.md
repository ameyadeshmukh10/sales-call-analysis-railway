# Agent: call-structure

**Stage B · per call.** Map the actual flow of the call — the order of topics,
where discovery happened, where the pitch landed, where pricing came up — so it
can later be compared against outcomes.

> Requires `speaker_attribution`. Read `docs/analysis_rules.md`. Cite by turn
> index. Emit ONLY the schema below.

## Inputs
```bash
python -m skills.store_io.context_loader context '{"call_id":"<CALL_ID>"}'
python -m skills.store_io.results_io read '{"call_id":"<CALL_ID>","agent":"speaker_attribution"}'
```

## Method
Segment the call into ordered phases, each with start/end turn indices:
`name ∈ {open, discovery, pitch, demo, pricing, objection, next_steps, smalltalk, other}`.
Phases can repeat (e.g. discovery → pitch → more discovery). Then assess:
- `followed_expected_sequence`: did it roughly follow open → discovery → pitch/demo
  → pricing → next steps (discovery before pitch)? boolean.
- `time_to_first_discovery_q`: turn index of the first real discovery question
  (null if none).
- `sequence_notes`: 1–3 sentences on the flow — e.g. "pitched before discovering",
  "strong discovery but no next step", "pricing came up unprompted from the buyer".
- `dead_air_or_derail`: notable derailments, long monologues, or lost threads.

For degenerate transcripts, return a single `other` phase spanning all turns and
note it.

## Output schema (emit ONLY this JSON)
```json
{
  "schema_version": "1.0",
  "phases": [
    {"name": "open", "start_turn": 0, "end_turn": 6},
    {"name": "discovery", "start_turn": 7, "end_turn": 40},
    {"name": "pitch", "start_turn": 41, "end_turn": 120}
  ],
  "followed_expected_sequence": true,
  "time_to_first_discovery_q": 7,
  "sequence_notes": "...",
  "dead_air_or_derail": ["..."]
}
```

## Persist
```bash
python -m skills.store_io.results_io write < /tmp/cs.json   # {"call_id","agent":"call_structure","result":{...}}
```
