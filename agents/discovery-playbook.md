# Agent: discovery-playbook

**Stage D · corpus → deliverable.** Across all calls, identify which questions
consistently surfaced the highest-value information and correlated with
advancement, and assemble a ranked, reusable discovery-question playbook.

> Read `docs/analysis_rules.md`. Every recommended question cites the calls it
> worked on. Emit the schema AND write the versioned deliverable.

## Inputs
```bash
python -m skills.corpus.corpus_aggregator
python -m skills.store_io.results_io read '{"call_id":"__corpus__","agent":"best_performing_call"}'
# pull rep questions + discovery scores from high vs low performers:
python -m skills.store_io.results_io read '{"call_id":"<CALL_ID>","agent":"rep_talk_extraction"}'
python -m skills.store_io.results_io read '{"call_id":"<CALL_ID>","agent":"discovery_quality"}'
```

## Method
Compare the questions asked on high-discovery-score / high-composite calls vs low
ones. Cluster effective questions by what they uncover (current motion, pain
quantification, decision process, signal readiness, success criteria). Rank them
by how reliably they surfaced usable pain / advanced the call. Each playbook entry
is a `finding` (the question + why it works + when to ask) with quantified
`support` and example calls. Add `recommendations` for sequencing the questions.

Carry the limitation block.

## Output schema (shared Stage D shape — emit ONLY this JSON)
```json
{
  "schema_version": "1.0",
  "findings": [
    {"claim": "Asking 'what does your current outbound motion look like?' early reliably surfaces capacity pain",
     "support": {"n_calls": 12, "pct": 39.0, "example_calls": ["<id>"]}}
  ],
  "recommendations": ["Open discovery with current-motion before pitching any capability"],
  "limitation_block": "<verbatim>",
  "corpus_stats": {"n_calls": 61, "mean_discovery_score": 0}
}
```

## Persist the versioned deliverable
```bash
python -m skills.corpus.outputs_versioner write < /tmp/dpb_out.json   # {"deliverable":"discovery_playbook","md":"<markdown>","data":{...}}
python -m skills.corpus.outputs_differ '{"deliverable":"discovery_playbook","to_v":<N>}'
python -m skills.store_io.results_io write < /tmp/dpb.json   # {"call_id":"__corpus__","agent":"discovery_playbook","result":{...}}
```
Prepend the changelog to the top of `vN.md`.
