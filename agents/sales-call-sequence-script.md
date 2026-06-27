# Agent: sales-call-sequence-script

**Stage D · corpus → deliverable.** Across all calls, informed by `call_structure`
+ the derived rubric, determine the optimal sequence of discovery → story →
activities within a call, and produce a repeatable call flow / script.

> Read `docs/analysis_rules.md`. Cite the calls each recommendation is drawn from.
> Emit the schema AND write the versioned deliverable.

## Inputs
```bash
python -m skills.corpus.corpus_aggregator
python -m skills.store_io.results_io read '{"call_id":"__corpus__","agent":"best_performing_call"}'
python -m skills.store_io.results_io read '{"call_id":"__corpus__","agent":"rubric_derivation"}'
# call-structure of high vs low performers:
python -m skills.store_io.results_io read '{"call_id":"<CALL_ID>","agent":"call_structure"}'
```

## Method
Compare the phase sequences of high-composite vs low calls (from `call_structure`):
where discovery happened relative to pitch, time-to-first-discovery-question,
where pricing landed, whether a next step was secured. Derive the flow that the
better calls share. Each `finding` is a sequence insight with quantified support;
`recommendations` assemble the repeatable flow (open → discovery → story/demo →
pricing → next step) with the specifics this product needs (e.g. "surface a
prior-vendor-failure objection early and address quality up front").

Carry the limitation block.

## Output schema (shared Stage D shape — emit ONLY this JSON)
```json
{
  "schema_version": "1.0",
  "findings": [
    {"claim": "Top calls reached a discovery question within the first ~5 minutes; low calls pitched first",
     "support": {"n_calls": 8, "pct": 26.0, "example_calls": ["<id>"]}}
  ],
  "recommendations": ["Earn the right to pitch: one strong discovery question before any capability"],
  "limitation_block": "<verbatim>",
  "corpus_stats": {"n_calls": 61, "mean_time_to_first_discovery_q": 0}
}
```

## Persist the versioned deliverable
```bash
python -m skills.corpus.outputs_versioner write < /tmp/seq_out.json   # {"deliverable":"sales_call_sequence_script","md":"<markdown>","data":{...}}
python -m skills.corpus.outputs_differ '{"deliverable":"sales_call_sequence_script","to_v":<N>}'
python -m skills.store_io.results_io write < /tmp/seq.json   # {"call_id":"__corpus__","agent":"sales_call_sequence_script","result":{...}}
```
Prepend the changelog to the top of `vN.md`.
