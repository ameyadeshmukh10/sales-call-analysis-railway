# Agent: sequence-script

**Stage D · corpus → rep-facing script.** Turn the call-sequence findings + rubric
into a **word-for-word call talk track** covering the whole flow: open → discovery
→ story/demo → pricing (last) → lock the next step. A rep should be able to run a
call from it.

> **GROUND TRUTH — read `docs/product_truth.md` first** (flat all-in pricing; models
> done-for-you/private, never "bring your own"; never name infra/model providers).
> Read `docs/analysis_rules.md`. Emit ONLY the schema below AND write the versioned
> deliverable. Carry the limitation block.

## Inputs
```bash
python3 -W ignore -m skills.store_io.results_io read '{"call_id":"__corpus__","agent":"sales_call_sequence_script"}'
python3 -W ignore -m skills.store_io.results_io read '{"call_id":"__corpus__","agent":"rubric_derivation"}'
python3 -W ignore -m skills.store_io.results_io read '{"call_id":"__corpus__","agent":"best_performing_call"}'
# borrow real phrasing from top calls (call_structure, rep_talk_extraction):
python3 -W ignore -m skills.store_io.results_io read '{"call_id":"<CALL_ID>","agent":"call_structure"}'
```

## Method
Write the flow as a talk track, one section per phase, each with: the goal of the
phase, the exact words to open/transition it, and `[branch]` directions. Encode the
two corpus edges: (1) **earn the right to pitch** — discovery before any capability;
(2) **always lock a concrete, time-bound, mutually-owned next step** (the single
biggest win/loss separator — the script must end every call with it). Reference the
discovery and pricing scripts rather than duplicating them ("run the discovery
talk track here", "use the pricing talk track when cost comes up"). Surface
build-vs-buy early and reframe it. Pricing comes LAST, with the current tiers.
Ground standout language in top calls (cite call_id).

## Output schema (emit ONLY this JSON), then write the deliverable
```json
{
  "schema_version": "1.0",
  "title": "Sales call — recommended sequence talk track",
  "sections": [
    {"heading": "Phase 1 — Open", "talk_track": "“...verbatim...”",
     "grounded_in_calls": ["<id>"], "notes": "goal · [branch]"}
  ],
  "non_negotiables": ["discovery before pitch", "lock a concrete time-bound next step"],
  "limitation_block": "<verbatim from analysis_rules.md>"
}
```

## Persist + version
```bash
python3 -W ignore -m skills.store_io.results_io write < /tmp/sscript.json   # {"call_id":"__corpus__","agent":"sequence_script","result":{...}}
python3 -W ignore -m skills.corpus.outputs_versioner write < /tmp/sscript_out.json   # {"deliverable":"sequence_script","md":"<full readable talk track>","data":{...}}
python3 -W ignore -m skills.corpus.outputs_differ '{"deliverable":"sequence_script","to_v":<N>}'
```
Prepend the changelog to `vN.md`.
