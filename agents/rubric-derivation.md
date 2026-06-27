# Agent: rubric-derivation

**Stage C · corpus.** Derive OUR OWN rubric for what good looks like — for this
product specifically — by comparing high-performing calls against low ones across
the Stage B dimensions. Do not import MEDDIC/SPIN wholesale; let the rubric emerge
from our winning calls, and cite the calls each dimension is drawn from.

> Requires `best_performing_call` (run it first). Read `docs/analysis_rules.md`.
> Cite calls + turns. Emit ONLY the schema below AND write the deliverable.

## Inputs
```bash
python -m skills.store_io.results_io read '{"call_id":"__corpus__","agent":"best_performing_call"}'
```
Take the `top_k` (high performers) and the bottom of `ranked` (low performers,
excluding degenerate transcripts). For a handful of each, pull their Stage A/B
results to see WHAT differed:
```bash
python -m skills.store_io.results_io read '{"call_id":"<CALL_ID>","agent":"discovery_quality"}'
# ...and objection_handling, pricing_packaging_reaction, call_structure, commitment_next_step,
#    rep_talk_extraction, customer_voice_extraction
```

## Method
For each dimension (discovery, objection handling, pricing framing, call
structure, next-step securing), articulate **what good looks like for this
product**, grounded in what the top calls actually did and the bottom calls
didn't. Give each a `weight` (how much it separates high from low) and cite
`derived_from_calls` + `example_quotes` (call_id + turn + verbatim text). Capture
`anti_patterns` seen in low performers.

Honor the limitation block — with 2 won deals this is a *hypothesis* rubric to
refine as more calls land. Say so.

## Output schema (emit ONLY this JSON), then write the deliverable
```json
{
  "schema_version": "1.0",
  "rubric": [
    {"dimension": "discovery", "what_good_looks_like": "...", "weight": 0.25,
     "derived_from_calls": ["<id>"], "example_quotes": [{"call_id": "<id>", "turn": 18, "text": "..."}]}
  ],
  "anti_patterns": [{"pattern": "pitched before discovering", "from_calls": ["<id>"]}],
  "limitation_block": "<verbatim from analysis_rules.md>"
}
```

## Persist + version the deliverable
```bash
python -m skills.store_io.results_io write < /tmp/rubric.json   # {"call_id":"__corpus__","agent":"rubric_derivation","result":{...}}
# Write the human deliverable (markdown) + structured data, versioned:
python -m skills.corpus.outputs_versioner write < /tmp/rubric_out.json   # {"deliverable":"rubric","md":"<markdown rubric>","data":{...same result...}}
python -m skills.corpus.outputs_differ '{"deliverable":"rubric","to_v":<N>}'
```
Prepend the returned changelog to the top of the `vN.md` you wrote (or note it's v1).
