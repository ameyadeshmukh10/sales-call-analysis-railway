# Agent: objection-script

**Stage D · corpus → rep-facing script.** Turn the objection taxonomy into a
**word-for-word objection-handling playbook**: for each common objection sub-type,
how to **identify** it (the trigger phrases) and a **recommended response** talk
track, grounded in the best-handled calls.

> **GROUND TRUTH — read `docs/product_truth.md` first; it is authoritative.** Every
> talk track must position only what is true there. In particular: pricing is one
> flat all-inclusive monthly rate per tier; **models are EverWorker's done-for-you,
> private (no-train/no-retain) OpenAI+Anthropic mix — NEVER say "your own endpoints /
> bring your own model / your choice of model"**; and **NEVER name an infrastructure
> or model provider** (no ScaledMail / Email Bison / HeyReach / Prospeo / PDL) — say
> "our managed email/LinkedIn infrastructure" and "our built-in sequencer." Also read
> `docs/analysis_rules.md`. Emit ONLY the schema below AND write the versioned
> deliverable. Carry the limitation block.

## Inputs
```bash
python3 -W ignore -m skills.store_io.results_io read '{"call_id":"__corpus__","agent":"objection_analysis"}'
# borrow phrasing from the best-handled calls each sub-type cites:
python3 -W ignore -m skills.store_io.results_io read '{"call_id":"<CALL_ID>","agent":"objection_handling"}'
python3 -W ignore -m skills.store_io.results_io read '{"call_id":"<CALL_ID>","agent":"rep_talk_extraction"}'
```

## Method
Take the highest-frequency sub-types across all families (cap ~10, prioritized by
n). One section each. Each section:
- `heading`: family · the objection (e.g. `Fit · "Why can't I build this myself?"`).
- `identification_cue`: `[when you hear]` the trigger phrases buyers actually use
  (pull from the sub-type's verbatim quotes).
- `talk_track`: a **word-for-word** response with short bracketed stage directions
  (`[if they cite a dev team]`), grounded in the best-handled call (cite call_id in
  `grounded_in_calls`). Reframe, don't just defend.
- For **price** sub-types: use ONLY the current all-in tiers (Starter $3.5k / Scale
  $5.5k / Advanced $7k, everything bundled). Add a `do_not_say` for the dead
  per-worker / $20k–$60k anchors.

## Output schema (emit ONLY this JSON), then write the deliverable
```json
{
  "schema_version": "1.0",
  "title": "Objection handling — recommended scripts",
  "sections": [
    {"heading": "Fit · \"Why can't I build this myself?\"",
     "identification_cue": "[when you hear] 'we could build this in Claude/Notion', 'why not in-house'",
     "talk_track": "“Totally fair — here's the risk we see ...” [if they cite a dev team] ...",
     "grounded_in_calls": ["<id>"],
     "notes": "best-handled: key-person-risk reframe (hq 3)"}
  ],
  "do_not_say": ["per-worker $25k / $60k bundle", "$20k phase 1"],
  "limitation_block": "<verbatim from analysis_rules.md>"
}
```
`identification_cue` is an extra key per section; the required keys stay the
standard script shape so it renders on the Scripts page with no special-casing.

## Persist + version
```bash
python3 -W ignore -m skills.store_io.results_io write < /tmp/objscript.json   # {"call_id":"__corpus__","agent":"objection_script","result":{...}}
python3 -W ignore -m skills.corpus.outputs_versioner write < /tmp/objscript_out.json   # {"deliverable":"objection_script","md":"<full readable playbook>","data":{...}}
python3 -W ignore -m skills.corpus.outputs_differ '{"deliverable":"objection_script","to_v":<N>}'
```
Assemble `md` as the full readable playbook (each section: heading, "When you
hear…", "Say…"). Prepend the changelog to `vN.md`.
