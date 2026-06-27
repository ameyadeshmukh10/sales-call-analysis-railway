# Agent: discovery-quality

**Stage B · per call.** Score how well the rep ran discovery: the questions they
asked, what those questions surfaced, and what they should have asked but didn't.

> Requires `speaker_attribution`. Read `docs/analysis_rules.md`. Cite by turn
> index. Emit ONLY the schema below.

## Inputs
```bash
python -m skills.store_io.context_loader context '{"call_id":"<CALL_ID>"}'
python -m skills.store_io.results_io read '{"call_id":"<CALL_ID>","agent":"speaker_attribution"}'
python -m skills.store_io.results_io read '{"call_id":"<CALL_ID>","agent":"rep_talk_extraction"}'
```
If the transcript is degenerate (near-silent / hallucinated — very few turns, one
repeated token), set `score: 0`, note it, and persist; do not invent discovery.

## Method
- Compute `open_question_ratio` = open questions / total rep questions.
- `pains_uncovered`: count of distinct customer pains the questions actually
  surfaced (cross-check the customer turns).
- `bant`: did discovery touch Budget, Authority, Need, Timeline? Booleans.
- `strengths` / `gaps`: what the rep did well; what they missed (e.g. never asked
  about current tooling, didn't quantify the pain, didn't find the decision
  process). Gaps should name questions that *should* have been asked.
- `score` 0–100: holistic discovery quality for THIS product (signals-to-meetings
  outbound). Reward open questions that advanced the call and surfaced usable pain.

## Output schema (emit ONLY this JSON)
```json
{
  "schema_version": "1.0",
  "score": 0,
  "open_question_ratio": 0.0,
  "pains_uncovered": 0,
  "bant": {"budget": false, "authority": false, "need": false, "timeline": false},
  "strengths": ["..."],
  "gaps": ["should have asked about current outbound tooling"],
  "depth_notes": "1-3 sentences",
  "evidence_turns": [12, 18, 30]
}
```

## Persist
```bash
python -m skills.store_io.results_io write < /tmp/dq.json   # {"call_id","agent":"discovery_quality","result":{...}}
```
