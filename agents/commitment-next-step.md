# Agent: commitment-next-step

**Stage B · per call.** Extract the concrete forward commitment the call ended
with. A secured, specific, mutually-owned next step is a strong leading indicator
of advancement, so judge it strictly.

> Requires `speaker_attribution`. Read `docs/analysis_rules.md`. Cite by turn
> index. Emit ONLY the schema below.

## Inputs
```bash
python -m skills.store_io.context_loader context '{"call_id":"<CALL_ID>"}'
python -m skills.store_io.results_io read '{"call_id":"<CALL_ID>","agent":"speaker_attribution"}'
```

## Method
Look at the closing portion of the call. Determine:
- `next_step_secured`: was a concrete next step actually agreed (not just "we'll be
  in touch")? boolean.
- `next_step_type ∈ {meeting, demo, proposal, pilot, intro, info_send, none}`.
- `who_owns ∈ {rep, customer, mutual}`.
- `due_by`: any date/timeframe stated (verbatim), or null.
- `explicit_quote`: the verbatim line where it was agreed (or null).
- `strength` 0–3: 0 = none/vague, 1 = soft ("send me info"), 2 = scheduled-ish,
  3 = firm mutual commitment with a time and owner.

## Output schema (emit ONLY this JSON)
```json
{
  "schema_version": "1.0",
  "next_step_secured": true,
  "next_step_type": "demo",
  "who_owns": "mutual",
  "due_by": "next Tuesday",
  "explicit_quote": "let's get the team on a demo next Tuesday",
  "strength": 3
}
```

## Persist
```bash
python -m skills.store_io.results_io write < /tmp/ns.json   # {"call_id","agent":"commitment_next_step","result":{...}}
```
