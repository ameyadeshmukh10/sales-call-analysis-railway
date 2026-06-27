# Agent: competitive-mention

**Stage B · per call.** Detect every competitor reference and how it was
positioned. Feeds battlecards and packaging.

> Requires `speaker_attribution`. Read `docs/analysis_rules.md` and the competitor
> list in `docs/interpretation.md`. Cite by turn index. Emit ONLY the schema.

## Inputs
```bash
python -m skills.store_io.context_loader context '{"call_id":"<CALL_ID>"}'
python -m skills.store_io.results_io read '{"call_id":"<CALL_ID>","agent":"speaker_attribution"}'
```

## Method
Find references to competitors / alternatives (11x, Artisan, Outreach,
Salesforce/Agentforce, Clay, Apollo, ZoomInfo, "build it ourselves with
Claude/GPT", in-house SDRs, agencies). For each:
- `name`, `mentioned_by ∈ {rep, customer}`, `turn`, short `context`,
  `sentiment ∈ {positive, neutral, negative}` toward that competitor.
- `prior_vendor_failure_cited`: did the buyer say they tried an AI-SDR/tool that
  failed? (Strong signal for the quality-objection narrative.)

If none: empty list, `n_mentions: 0`, `prior_vendor_failure_cited: false`.

## Output schema (emit ONLY this JSON)
```json
{
  "schema_version": "1.0",
  "competitors": [
    {"name": "11x", "mentioned_by": "customer", "turn": 64,
     "context": "tried it, emails were obviously AI", "sentiment": "negative"}
  ],
  "prior_vendor_failure_cited": true,
  "n_mentions": 1
}
```

## Persist
```bash
python -m skills.store_io.results_io write < /tmp/comp.json   # {"call_id","agent":"competitive_mention","result":{...}}
```
