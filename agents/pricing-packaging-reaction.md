# Agent: pricing-packaging-reaction

**Stage B · per call.** Isolate every moment pricing, packaging, or bundling came
up; capture the rep's framing and the buyer's reaction. This feeds the pricing
recommendations directly, so be precise about what was said.

> Requires `speaker_attribution`. **Ground truth: `docs/product_truth.md`** (flat
> all-in pricing; models done-for-you/private; provider names are internal-only).
> Read `docs/analysis_rules.md`. Cite by turn index. Emit ONLY the schema.

## Current pricing truth (see docs/interpretation.md for detail)
One all-in fixed cost per tier — **Starter $3.5k / Scale $5.5k / Advanced $7k per
month**. Everything is bundled (LLM + consumption, email & LinkedIn account-rental
infrastructure, the built-in Email Bison email sequencer and HeyReach LinkedIn
sequencer — both whitelabeled, never named/priced separately, and Scale/Advanced
add native Prospeo + People Data Labs enrichment). **There is no 4-phase upgrade
sequence and no per-phase add-on fees** — that model is dead.

## Method
- `pricing_discussed`: was pricing/packaging discussed at all?
- `tiers_mentioned`: which of {Starter, Scale, Advanced, other} came up.
- `price_objection`: did the buyer push back on price specifically?
- `buyer_reaction ∈ {positive, neutral, negative, none}`.
- `bundling_signals`: reactions to the all-in/bundled model — e.g. relief at "no
  procurement / one fixed cost", confusion about what's included, questions about
  whether infra/LLM/data are extra, or references to **outdated** pricing
  (~$20k/yr, paying for Bison/data separately, the old phased model). Each as a
  short phrase. This is the highest-value field — capture it carefully.
- `anchor_value`: any explicit number the buyer anchored on (their words), or null.
- `rep_framing`: one line on how the rep presented price/packaging.
- `evidence_turns`: the turns where pricing/packaging was discussed.

If pricing never came up: `pricing_discussed: false` and empty lists.

## Output schema (emit ONLY this JSON)
```json
{
  "schema_version": "1.0",
  "pricing_discussed": true,
  "tiers_mentioned": ["Scale"],
  "price_objection": false,
  "buyer_reaction": "positive",
  "bundling_signals": ["relieved that email + LinkedIn infra and data are included"],
  "anchor_value": null,
  "rep_framing": "positioned Scale as one predictable fixed cost vs assembling a stack",
  "evidence_turns": [180, 184, 191]
}
```

## Persist
```bash
python -m skills.store_io.results_io write < /tmp/pp.json   # {"call_id","agent":"pricing_packaging_reaction","result":{...}}
```
