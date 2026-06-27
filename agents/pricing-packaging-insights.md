# Agent: pricing-packaging-insights

**Stage D · corpus → deliverable.** Across all calls: where does pricing create
friction, which bundles resonate, how does the all-in fixed-cost model land, and
what would reduce friction? Produces recommendations to evolve
pricing/packaging/bundling.

> **Ground truth: `docs/product_truth.md`** (flat all-in pricing; models
> done-for-you/private; never name infra/model providers in any recommendation).
> Read `docs/analysis_rules.md`. Every claim cites supporting calls. Emit the schema
> AND write the versioned deliverable.

## Inputs
```bash
python -m skills.corpus.corpus_aggregator    # corpus tallies incl. pricing block
# drill into specific calls as needed:
python -m skills.store_io.results_io read '{"call_id":"<CALL_ID>","agent":"pricing_packaging_reaction"}'
```

## Method
Use the aggregator's `pricing` block (discussed rate, tiers mentioned, price
objections, buyer_reaction distribution, bundling_signals) plus the objection
families. Synthesize findings, each with quantified support (`n_calls`, `pct`,
`example_calls`). Focus on: which tier buyers gravitate to and why; reactions to
the all-in bundled model (relief vs confusion); whether anyone references outdated
pricing/phased model; where price objections cluster (segment by ICP/persona/size
via icp_fit_tagger). Then give concrete `recommendations` to reduce friction.

Carry the limitation block. Do not overclaim from a 61-call, 2-rep sample.

## Output schema (shared Stage D shape — emit ONLY this JSON)
```json
{
  "schema_version": "1.0",
  "findings": [
    {"claim": "Buyers respond positively to the all-in fixed cost when framed against assembling a stack",
     "support": {"n_calls": 9, "pct": 30.0, "example_calls": ["<id>"]}}
  ],
  "recommendations": ["Lead pricing with the 'one fixed cost, nothing to procure' frame"],
  "limitation_block": "<verbatim>",
  "corpus_stats": {"n_calls": 61, "pricing_discussed_pct": 0.0}
}
```

## Persist the versioned deliverable
```bash
python -m skills.corpus.outputs_versioner write < /tmp/ppi_out.json   # {"deliverable":"pricing_packaging_insights","md":"<markdown>","data":{...}}
python -m skills.corpus.outputs_differ '{"deliverable":"pricing_packaging_insights","to_v":<N>}'
# also store the structured result for the record:
python -m skills.store_io.results_io write < /tmp/ppi.json   # {"call_id":"__corpus__","agent":"pricing_packaging_insights","result":{...}}
```
Prepend the changelog from the differ to the top of `vN.md`.
