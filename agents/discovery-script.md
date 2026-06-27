# Agent: discovery-script

**Stage D · corpus → rep-facing script.** Turn the discovery playbook into a
**word-for-word discovery talk track**: the ranked questions in the right order,
with the transitions and follow-ups that the best calls used, so a rep can run
discovery from it directly.

> Read `docs/analysis_rules.md`. Emit ONLY the schema below AND write the versioned
> deliverable. Carry the limitation block.

## Inputs
```bash
python3 -W ignore -m skills.store_io.results_io read '{"call_id":"__corpus__","agent":"discovery_playbook"}'
python3 -W ignore -m skills.store_io.results_io read '{"call_id":"__corpus__","agent":"best_performing_call"}'
# borrow real phrasing from high-discovery calls:
python3 -W ignore -m skills.store_io.results_io read '{"call_id":"<CALL_ID>","agent":"rep_talk_extraction"}'
python3 -W ignore -m skills.store_io.results_io read '{"call_id":"<CALL_ID>","agent":"discovery_quality"}'
```

## Method
Sequence the playbook's highest-yield question clusters into a talk track:
current-motion → bottleneck (the highest-yield, under-asked question) → quantify
(meetings/week vs target, ACV, TAM) → success criteria → **budget & timeline** (the
corpus's worst-covered dimensions — make the script force them) → decision process.
For each, give the exact question(s) to ask, a one-line why, the transition into it,
and a `[follow-up if the buyer is vague]` branch. Ground standout phrasing in real
high-scoring calls (cite call_id). Keep the rep's talk-share balanced; the script
should make the buyer talk.

## Output schema (emit ONLY this JSON), then write the deliverable
```json
{
  "schema_version": "1.0",
  "title": "Discovery — recommended talk track",
  "sections": [
    {"heading": "Open / current motion", "talk_track": "“...verbatim question(s)...”",
     "grounded_in_calls": ["<id>"], "notes": "why it works · [follow-up if vague]"}
  ],
  "questions_to_never_skip": ["budget", "timeline"],
  "limitation_block": "<verbatim from analysis_rules.md>"
}
```

## Persist + version
```bash
python3 -W ignore -m skills.store_io.results_io write < /tmp/dscript.json   # {"call_id":"__corpus__","agent":"discovery_script","result":{...}}
python3 -W ignore -m skills.corpus.outputs_versioner write < /tmp/dscript_out.json   # {"deliverable":"discovery_script","md":"<full readable talk track>","data":{...}}
python3 -W ignore -m skills.corpus.outputs_differ '{"deliverable":"discovery_script","to_v":<N>}'
```
Prepend the changelog to `vN.md`.
